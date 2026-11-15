import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from consumos.services import PedidoRechazado
from empresas.models import Empresa
from menus.services import disponibilidad, menu_publicado
from operadores.models import local_de_usuario
from trabajadores.models import Trabajador

from . import despacho
from .services import cambiar_plato


def es_administrador(user):
    return user.is_authenticated and user.is_staff


def _fecha(valor):
    return parse_date(valor or "") or timezone.localdate()


def _url_lista(empresa, fecha):
    return f"{reverse('despacho:lista')}?empresa={empresa.pk}&fecha={fecha:%Y-%m-%d}"


@user_passes_test(es_administrador, login_url="login")
def lista(request):
    """Lista nominal de despacho de una empresa para un día (hoy por defecto)."""
    local = local_de_usuario(request.user)
    empresas = Empresa.objects.filter(activa=True)
    empresa = None
    if request.GET.get("empresa", "").isdigit():
        empresa = empresas.filter(pk=int(request.GET["empresa"])).first()
    fecha = _fecha(request.GET.get("fecha"))
    contexto = {"empresas": empresas, "empresa": empresa, "fecha": fecha, "local": local}
    if empresa is None or local is None:
        return render(request, "pedidos/despacho.html", contexto)

    menu = menu_publicado(local, fecha)
    pedidos = {p.consumo.trabajador_id: p for p in despacho.pedidos_de_despacho(empresa, local, fecha)}
    filas = []
    for trabajador in Trabajador.objects.filter(empresa=empresa, activo=True, eliminado_en__isnull=True):
        pedido = pedidos.get(trabajador.pk)
        filas.append({
            "id": trabajador.pk,
            "nombre": str(trabajador),
            "rut": trabajador.rut,
            "token": str(uuid.uuid4()),  # idempotencia: reenviar la lista no duplica pedidos
            "pedido": None if pedido is None else {
                "id": pedido.pk,
                "folio": pedido.folio_texto,
                "estado": pedido.estado,
                "items": [
                    {"id": i.pk, "tiempo": i.plato.tiempo_id, "plato": i.plato_id, "acompanamiento": i.acompanamiento_id, "texto": str(i)}
                    for i in pedido.items.select_related("plato")
                ],
            },
        })
    contexto.update({
        "menu": menu,
        "abierta": despacho.lista_abierta(empresa, local, fecha),
        "hora_cierre": despacho.hora_cierre(empresa, local),
        "filas": filas,
        "datos": {
            "filas": filas,
            "menu": disponibilidad(menu) if menu else None,
            "url_disponibilidad": reverse("menus:disponibilidad", args=[menu.pk]) if menu else None,
        },
        "registrados": len(pedidos),
        "totales": despacho.totales_por_plato(pedidos.values()),
    })
    return render(request, "pedidos/despacho.html", contexto)


@user_passes_test(es_administrador, login_url="login")
@require_POST
def confirmar(request):
    """Registra los marcados, aplica los cambios de plato y anula los desmarcados."""
    empresa = get_object_or_404(Empresa, pk=request.POST.get("empresa"))
    fecha = _fecha(request.POST.get("fecha"))
    try:
        datos = json.loads(request.POST.get("lista", "{}"))
    except ValueError:
        datos = {}
    local = local_de_usuario(request.user)
    trabajadores = {
        t.pk: t for t in Trabajador.objects.filter(empresa=empresa, pk__in=[f.get("trabajador") for f in datos.get("nuevos", [])])
    }
    filas = []
    for fila in datos.get("nuevos", []):
        trabajador = trabajadores.get(fila.get("trabajador"))
        if trabajador is not None:
            filas.append({"trabajador": trabajador, "token": fila.get("token"), "seleccion": fila.get("seleccion", [])})
    quitar = list(despacho.pedidos_de_despacho(empresa, local, fecha).filter(pk__in=datos.get("quitar", []))) if local else []

    try:
        resultado = despacho.confirmar_lista(request.user, empresa, fecha, filas, quitar=quitar)
    except despacho.ErrorDespacho as error:
        messages.error(request, error.mensaje)
        return redirect(_url_lista(empresa, fecha))

    cambiados, errores_cambio = 0, []
    for cambio in datos.get("cambios", []):
        try:
            cambiar_plato(cambio.get("item"), cambio.get("plato"), cambio.get("acompanamiento"), request.user, "Cambio en la lista de despacho")
            cambiados += 1
        except PedidoRechazado as rechazo:
            errores_cambio.append(rechazo.mensaje)

    partes = []
    if resultado.creados:
        partes.append(f"{len(resultado.creados)} pedido(s) registrado(s)")
    if cambiados:
        partes.append(f"{cambiados} plato(s) cambiado(s)")
    if resultado.quitados:
        partes.append(f"{len(resultado.quitados)} quitado(s) de la lista")
    if partes:
        messages.success(request, ", ".join(partes).capitalize() + ".")
    for trabajador, _, mensaje in resultado.errores:
        messages.error(request, f"No se registró a {trabajador}: {mensaje}")
    for mensaje in errores_cambio:
        messages.error(request, f"No se cambió un plato: {mensaje}")
    if not (partes or resultado.errores or errores_cambio):
        messages.info(request, "No había cambios que guardar.")
    return redirect(_url_lista(empresa, fecha))
