import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from empresas.models import Empresa
from empresas.validators import normalizar_rut
from locales.models import Local
from menus.services import (
    ErrorMenu,
    disponibilidad,
    liberar,
    menu_publicado_de_usuario,
    renovar_reservas,
    reservar,
    ultima_seleccion,
)
from operadores.models import local_de_usuario
from trabajadores.models import Trabajador

from .models import Consumo, consumos_vigentes
from .services import (
    AnulacionInvalida,
    PedidoRechazado,
    anular_consumo,
    TrabajadorNoDisponible,
    estado_cupo,
    registrar_consumo_diario,
    registrar_pedido,
)


def operador_o_administrador(user):
    perfil = getattr(user, "perfil_operador", None)
    return user.is_authenticated and (user.is_staff or (perfil and perfil.activo))


@user_passes_test(lambda user: user.is_authenticated and user.is_staff, login_url="login")
def dashboard(request):
    hoy = timezone.localdate()
    consumos_hoy = consumos_vigentes().filter(fecha=hoy)
    empresas = (
        consumos_hoy.values("trabajador__empresa__nombre")
        .annotate(total=Count("id"))
        .order_by("trabajador__empresa__nombre")
    )
    locales = (
        consumos_hoy.values("local__nombre")
        .annotate(total=Count("id"))
        .order_by("local__nombre")
    )
    contexto = {
        "fecha": hoy,
        "total_hoy": consumos_hoy.count(),
        "empresas": empresas,
        "locales": locales,
        "ultimos_consumos": consumos_hoy.select_related(
            "trabajador", "trabajador__empresa"
        )[:10],
    }
    return render(request, "consumos/dashboard.html", contexto)


@user_passes_test(operador_o_administrador, login_url="login")
def historial(request):
    es_admin = request.user.is_staff
    consumos = Consumo.objects.select_related(
        "trabajador", "trabajador__empresa", "operador", "local", "anulado_por", "pedido"
    )

    if es_admin:
        fecha = parse_date(request.GET.get("fecha", "") or "")
    else:
        # El operador solo consulta la jornada en curso.
        fecha = timezone.localdate()
    empresa_id = request.GET.get("empresa", "")
    local_id = request.GET.get("local", "")
    trabajador_id = request.GET.get("trabajador", "") if es_admin else ""
    rut_ingresado = request.GET.get("rut", "").strip()
    rut = ""
    rut_error = None
    if rut_ingresado:
        try:
            rut = normalizar_rut(rut_ingresado)
        except ValidationError as error:
            rut_error = error.messages[0]

    if fecha:
        consumos = consumos.filter(fecha=fecha)
    if empresa_id.isdigit():
        consumos = consumos.filter(trabajador__empresa_id=int(empresa_id))
    if local_id.isdigit():
        consumos = consumos.filter(local_id=int(local_id))
    if trabajador_id.isdigit():
        consumos = consumos.filter(trabajador_id=int(trabajador_id))
    if rut:
        consumos = consumos.filter(trabajador__rut=rut)
    elif rut_error:
        consumos = consumos.none()

    pagina = Paginator(consumos, 50).get_page(request.GET.get("pagina"))
    anulados = consumos.filter(anulado=True).count()
    filtros = request.GET.copy()
    filtros.pop("pagina", None)
    contexto = {
        "consumos": pagina,
        "total_vigentes": pagina.paginator.count - anulados,
        "total_anulados": anulados,
        "es_admin": es_admin,
        "empresas": Empresa.objects.all(),
        "locales": Local.objects.all(),
        "local_seleccionado": local_id,
        # Solo se listan los trabajadores de la empresa elegida: cargar la nómina
        # completa de todas las empresas haría la página lenta.
        "trabajadores": (
            Trabajador.objects.filter(empresa_id=int(empresa_id))
            if es_admin and empresa_id.isdigit()
            else Trabajador.objects.none()
        ),
        "fecha_seleccionada": fecha,
        "empresa_seleccionada": empresa_id,
        "trabajador_seleccionado": trabajador_id,
        "rut_ingresado": rut_ingresado,
        "rut_error": rut_error,
        "filtros_query": filtros.urlencode(),
    }
    return render(request, "consumos/historial.html", contexto)


def _ultimos_del_operador(usuario, fecha, limite=5):
    return [
        {
            "worker": str(consumo.trabajador),
            "company": str(consumo.trabajador.empresa),
            "time": timezone.localtime(consumo.registrado_en).strftime("%H:%M"),
            "number": consumo.numero,
            "manual": consumo.metodo == Consumo.METODO_RUT,
            "folio": consumo.pedido.folio_texto if getattr(consumo, "pedido", None) else None,
        }
        for consumo in consumos_vigentes().filter(operador=usuario, fecha=fecha)
        .select_related("trabajador", "trabajador__empresa", "pedido")
        .order_by("-registrado_en")[:limite]
    ]


def _identificar_trabajador(request):
    """Trabajador escaneado (campo «token», QR) o elegido por RUT («trabajador_id», manual)."""
    trabajador_id = request.POST.get("trabajador_id", "").strip()
    if trabajador_id:
        trabajador = None
        if trabajador_id.isdigit():
            trabajador = Trabajador.objects.select_related("empresa").filter(pk=int(trabajador_id)).first()
        if trabajador is None:
            return None, Consumo.METODO_RUT, "Trabajador no encontrado."
        return trabajador, Consumo.METODO_RUT, None
    try:
        token_qr = uuid.UUID(request.POST.get("token", "").strip())
    except ValueError:
        return None, Consumo.METODO_QR, "QR no válido."
    trabajador = Trabajador.objects.select_related("empresa").filter(token_qr=token_qr).first()
    if trabajador is None:
        return None, Consumo.METODO_QR, "QR no válido o dado de baja."
    return trabajador, Consumo.METODO_QR, None


MENSAJE_NO_DISPONIBLE = "Trabajador inactivo o desvinculado. No puede registrar almuerzos."


def _total_hoy(hoy):
    return consumos_vigentes().filter(fecha=hoy).count()


def _respuesta_error(mensaje, hoy, status=400, **extra):
    return JsonResponse(
        {"ok": False, "status": "error", "message": mensaje, "today_total": _total_hoy(hoy), **extra}, status=status
    )


def _respuesta_cupo_agotado(trabajador, metodo, usados, cupo, hoy, status=200):
    ultimo = consumos_vigentes().filter(trabajador=trabajador, fecha=hoy).order_by("-registrado_en").first()
    return JsonResponse({
        "ok": True,
        "status": "duplicate",
        "message": f"Cupo diario agotado ({usados} de {cupo}).",
        "worker": str(trabajador),
        "company": str(trabajador.empresa),
        "used": usados,
        "quota": cupo,
        "manual": metodo == Consumo.METODO_RUT,
        "time": timezone.localtime(ultimo.registrado_en).strftime("%H:%M") if ultimo else "",
        "today_total": _total_hoy(hoy),
    }, status=status)


@user_passes_test(operador_o_administrador, login_url="login")
def escaner(request):
    hoy = timezone.localdate()

    if request.method != "POST":
        return render(
            request,
            "consumos/escaner.html",
            {
                "total_hoy": _total_hoy(hoy),
                "ultimos": _ultimos_del_operador(request.user, hoy),
                "local": local_de_usuario(request.user),
                "con_menu": menu_publicado_de_usuario(request.user, hoy) is not None,
            },
        )

    trabajador, metodo, error = _identificar_trabajador(request)
    if error:
        return _respuesta_error(error, hoy)

    menu = menu_publicado_de_usuario(request.user, hoy)
    if menu is not None:
        # v0.2: con menú publicado el escaneo no registra nada; abre la hoja de pedido.
        # El consumo nace al confirmar (registrar_pedido), que vuelve a validar todo con bloqueo.
        try:
            trabajador, usados, cupo = estado_cupo(trabajador.pk, hoy)
        except TrabajadorNoDisponible:
            return _respuesta_error(MENSAJE_NO_DISPONIBLE, hoy)
        if usados >= cupo:
            return _respuesta_cupo_agotado(trabajador, metodo, usados, cupo, hoy)
        return JsonResponse({
            "ok": True,
            "status": "seleccion",
            "worker": str(trabajador),
            "company": str(trabajador.empresa),
            "trabajador_id": trabajador.pk,
            "used": usados,
            "quota": cupo,
            "manual": metodo == Consumo.METODO_RUT,
            "selection_token": str(uuid.uuid4()),
            "menu": disponibilidad(menu),
            "previous": ultima_seleccion(request.user, hoy),
            "today_total": _total_hoy(hoy),
        })

    # v0.1: sin menú publicado hoy, el escaneo registra el almuerzo directamente.
    try:
        resultado = registrar_consumo_diario(trabajador.pk, request.user, fecha=hoy, metodo=metodo)
    except TrabajadorNoDisponible:
        return _respuesta_error(MENSAJE_NO_DISPONIBLE, hoy)

    datos = {
        "ok": True,
        "worker": str(trabajador),
        "company": str(trabajador.empresa),
        "used": resultado.usados,
        "quota": resultado.cupo,
        "number": resultado.consumo.numero,
        "manual": metodo == Consumo.METODO_RUT,
        "time": timezone.localtime(resultado.consumo.registrado_en).strftime("%H:%M"),
        "today_total": _total_hoy(hoy),
    }
    if resultado.creado:
        datos.update({
            "status": "registered",
            "message": f"Almuerzo {resultado.usados} de {resultado.cupo} registrado.",
        })
    else:
        datos.update({
            "status": "duplicate",
            "message": f"Cupo diario agotado ({resultado.usados} de {resultado.cupo}).",
        })
    return JsonResponse(datos)


def _token_seleccion(request):
    try:
        return uuid.UUID(request.POST.get("selection_token", "").strip())
    except ValueError:
        return None


@user_passes_test(operador_o_administrador, login_url="login")
@require_POST
def reservar_porcion(request):
    """El garzón tocó una opción: reserva 1 porción por 90 s para este comensal."""
    token = _token_seleccion(request)
    if token is None:
        return JsonResponse({"ok": False, "code": "seleccion_incompleta", "message": "Selección no válida."}, status=400)
    plato = request.POST.get("plato", "")
    acomp = request.POST.get("acompanamiento", "")
    if not plato.isdigit() or (acomp and not acomp.isdigit()):
        return JsonResponse({"ok": False, "code": "seleccion_incompleta", "message": "Selección no válida."}, status=400)
    try:
        reserva = reservar(request.user, token, int(plato), int(acomp) if acomp else None)
    except ErrorMenu as error:
        return JsonResponse({"ok": False, "code": error.codigo, "message": error.mensaje, "item": error.item}, status=409)
    return JsonResponse({"ok": True, **reserva})


@user_passes_test(operador_o_administrador, login_url="login")
@require_POST
def liberar_reservas(request):
    """Cancelar la hoja (todas las reservas) o quitar la opción de un tiempo."""
    token = _token_seleccion(request)
    if token is None:
        return JsonResponse({"ok": False}, status=400)
    tiempo = request.POST.get("tiempo", "")
    liberadas = liberar(request.user, token, int(tiempo) if tiempo.isdigit() else None)
    return JsonResponse({"ok": True, "released": liberadas})


@user_passes_test(operador_o_administrador, login_url="login")
@require_POST
def renovar(request):
    """Interacción en la hoja que no reserva ni libera: renueva 90 s las reservas vigentes."""
    token = _token_seleccion(request)
    if token is None:
        return JsonResponse({"ok": False}, status=400)
    return JsonResponse({"ok": True, "renewed": renovar_reservas(request.user, token)})


@user_passes_test(operador_o_administrador, login_url="login")
@require_POST
def confirmar_pedido(request):
    """Confirma el pedido: crea consumo, pedido y folio en una sola transacción."""
    hoy = timezone.localdate()
    trabajador, metodo, error = _identificar_trabajador(request)
    if error:
        return _respuesta_error(error, hoy, code="qr_invalido")
    token = _token_seleccion(request)
    try:
        seleccion = json.loads(request.POST.get("seleccion", "[]"))
    except ValueError:
        seleccion = None
    if token is None or not isinstance(seleccion, list):
        return _respuesta_error("Selección no válida.", hoy, code="seleccion_incompleta")

    try:
        resultado = registrar_pedido(trabajador.pk, request.user, token, seleccion, metodo=metodo, fecha=hoy)
    except PedidoRechazado as rechazo:
        if rechazo.codigo == "cupo_agotado":
            return _respuesta_cupo_agotado(trabajador, metodo, rechazo.usados, rechazo.cupo, hoy, status=409)
        return _respuesta_error(rechazo.mensaje, hoy, status=409, code=rechazo.codigo, item=rechazo.item)

    pedido = resultado.pedido
    return JsonResponse({
        "ok": True,
        "status": "registered",
        "created": resultado.creado,
        "message": f"Pedido {pedido.folio_texto} · {pedido.mesa_nombre}",
        "folio": pedido.folio_texto,
        "table": pedido.mesa_nombre,
        "items": [str(item) for item in resultado.items or pedido.items.all()],
        "worker": str(trabajador),
        "company": str(trabajador.empresa),
        "used": resultado.usados,
        "quota": resultado.cupo,
        "number": pedido.consumo.numero,
        "manual": metodo == Consumo.METODO_RUT,
        "time": timezone.localtime(pedido.consumo.registrado_en).strftime("%H:%M"),
        "today_total": _total_hoy(hoy),
    })


@user_passes_test(operador_o_administrador, login_url="login")
def buscar_por_rut(request):
    """Busca trabajadores vigentes por RUT para el registro manual."""
    try:
        rut = normalizar_rut(request.GET.get("rut", ""))
    except ValidationError as error:
        return JsonResponse({"ok": False, "message": error.messages[0]}, status=400)

    hoy = timezone.localdate()
    candidatos = []
    for trabajador in (
        Trabajador.objects.filter(rut=rut, activo=True, eliminado_en__isnull=True, empresa__activa=True)
        .select_related("empresa")
        .order_by("empresa__nombre")
    ):
        usados = consumos_vigentes().filter(trabajador=trabajador, fecha=hoy).count()
        candidatos.append({
            "id": trabajador.pk,
            "worker": str(trabajador),
            "company": str(trabajador.empresa),
            "used": usados,
            "quota": trabajador.cupo_diario,
        })
    if not candidatos:
        return JsonResponse({"ok": False, "message": "No hay trabajadores activos con ese RUT."}, status=404)
    return JsonResponse({"ok": True, "rut": rut, "results": candidatos})


@user_passes_test(lambda user: user.is_authenticated and user.is_staff, login_url="login")
@require_POST
def anular(request, consumo_id):
    """Anula un consumo (solo administrador, con motivo). Si tiene pedido, devuelve sus porciones."""
    try:
        consumo = anular_consumo(consumo_id, request.user, request.POST.get("motivo", ""))
    except AnulacionInvalida as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Consumo de {consumo.trabajador} anulado. No cuenta para el cupo ni se cobra.")
    destino = request.POST.get("volver", "")
    if not (destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()})):
        destino = reverse("consumos:historial")
    return redirect(destino)
