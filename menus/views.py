import hashlib
import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, HttpResponseNotModified
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from locales.models import Local
from operadores.models import local_de_usuario

from . import services
from .forms import AcompanamientoForm, AjusteForm, ItemForm, PlatoForm, TiempoForm
from .models import Acompanamiento, MenuDia, PlatoDia, TiempoMenu


def es_administrador(user):
    return user.is_authenticated and user.is_staff


def operador_o_administrador(user):
    perfil = getattr(user, "perfil_operador", None)
    return user.is_authenticated and (user.is_staff or (perfil and perfil.activo))


def respuesta_json_con_etag(request, datos):
    """JSON con ETag: si el cliente ya tiene esta versión responde 304 sin cuerpo."""
    cuerpo = json.dumps(datos, cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False)
    etag = '"' + hashlib.sha1(cuerpo.encode()).hexdigest()[:20] + '"'
    if request.headers.get("If-None-Match") == etag:
        respuesta = HttpResponseNotModified()
    else:
        respuesta = HttpResponse(cuerpo, content_type="application/json")
    respuesta["ETag"] = etag
    respuesta["Cache-Control"] = "no-cache"
    return respuesta


def _menu_url(menu):
    return f"{reverse('menus:menu_dia')}?local={menu.local_id}&fecha={menu.fecha:%Y-%m-%d}"


def _volver(menu):
    return redirect(_menu_url(menu))


# --- Menú del día ----------------------------------------------------------------------

@user_passes_test(es_administrador, login_url="login")
def menu_dia(request):
    locales = Local.objects.filter(activo=True)
    local = None
    if request.GET.get("local", "").isdigit():
        local = Local.objects.filter(pk=int(request.GET["local"])).first()
    local = local or local_de_usuario(request.user) or locales.first()
    fecha = parse_date(request.GET.get("fecha", "") or "") or timezone.localdate()
    menu = MenuDia.objects.filter(local=local, fecha=fecha).first() if local else None

    contexto = {
        "locales": locales,
        "local": local,
        "fecha": fecha,
        "menu": menu,
        "menus_anteriores": MenuDia.objects.filter(local=local).exclude(fecha=fecha)[:30] if local else [],
        "tiempos": TiempoMenu.objects.filter(activo=True),
        "plato_form": PlatoForm(),
        "acomp_form": AcompanamientoForm(),
    }
    if menu:
        estado = services.disponibilidad(menu)
        por_tiempo = {t["id"]: t["platos"] for t in estado["tiempos"]}
        contexto["secciones"] = [
            {"tiempo": tiempo, "platos": por_tiempo.get(tiempo.pk, [])}
            for tiempo in contexto["tiempos"]
        ]
    return render(request, "menus/menu_dia.html", contexto)


@user_passes_test(es_administrador, login_url="login")
@require_POST
def crear_menu(request):
    local = get_object_or_404(Local, pk=request.POST.get("local"))
    fecha = parse_date(request.POST.get("fecha", "")) or timezone.localdate()
    origen_id = request.POST.get("origen", "")
    try:
        if origen_id.isdigit():
            origen = get_object_or_404(MenuDia, pk=int(origen_id), local=local)
            menu = services.copiar_menu(origen, fecha, request.user)
            messages.success(request, f"Menú copiado del {origen.fecha:%d-%m-%Y}. Revísalo y publícalo.")
        else:
            menu, _ = MenuDia.objects.get_or_create(local=local, fecha=fecha)
    except services.ErrorMenu as error:
        messages.error(request, error.mensaje)
        return redirect(f"{reverse('menus:menu_dia')}?local={local.pk}&fecha={fecha:%Y-%m-%d}")
    return _volver(menu)


def _int_o_none(valor):
    return int(valor) if valor not in (None, "") else None


@user_passes_test(es_administrador, login_url="login")
@require_POST
def accion_menu(request, menu_id):
    """Acciones del administrador sobre el menú. Cada una pasa por menus.services."""
    menu = get_object_or_404(MenuDia, pk=menu_id)
    accion = request.POST.get("accion")
    tipo = request.POST.get("tipo") if request.POST.get("tipo") in ("plato", "acompanamiento") else "plato"
    item_id = request.POST.get("item", "")
    try:
        if accion == "publicar":
            services.publicar(menu, True, request.user)
            messages.success(request, "Menú publicado: los garzones ya lo ven en el escáner.")
        elif accion == "despublicar":
            services.publicar(menu, False, request.user)
            messages.warning(request, "Menú oculto: el escáner vuelve a registrar sin pedido.")
        elif accion == "agregar_plato":
            form = PlatoForm(request.POST)
            if not form.is_valid():
                raise services.ErrorMenu("formulario", "Revisa el nombre, el tiempo y las porciones del plato.")
            datos = form.cleaned_data
            services.crear_item(
                request.user, menu, datos["nombre"].strip(), datos["porciones"], datos["umbral_aviso"], tiempo=datos["tiempo"]
            )
        elif accion == "agregar_acompanamiento":
            plato = get_object_or_404(PlatoDia, pk=item_id, menu=menu)
            form = AcompanamientoForm(request.POST)
            if not form.is_valid():
                raise services.ErrorMenu("formulario", "Revisa el nombre y las porciones del acompañamiento.")
            datos = form.cleaned_data
            services.crear_item(
                request.user, menu, datos["nombre"].strip(), datos["porciones"], datos["umbral_aviso"], plato=plato
            )
        elif accion == "editar":
            form = ItemForm(request.POST)
            if not form.is_valid():
                raise services.ErrorMenu("formulario", "Revisa los datos del ítem.")
            datos = form.cleaned_data
            services.editar_item(
                request.user, tipo, _item_del_menu(menu, tipo, item_id).pk, datos["nombre"].strip(),
                datos["umbral_aviso"], datos["porciones"], cambiar_porciones=not menu.publicado,
            )
        elif accion == "ajustar":
            form = AjusteForm(request.POST)
            if not form.is_valid():
                raise services.ErrorMenu("formulario", "Indica las porciones y el motivo del ajuste.")
            services.ajustar_porciones(
                tipo, _item_del_menu(menu, tipo, item_id).pk, form.cleaned_data["porciones"], request.user,
                form.cleaned_data["motivo"],
            )
            messages.success(request, "Porciones ajustadas.")
        elif accion in ("agotar", "reactivar"):
            item = services.marcar_agotado(tipo, _item_del_menu(menu, tipo, item_id).pk, accion == "agotar", request.user)
            messages.success(request, f"{item.nombre}: {'Agotado' if item.agotado else 'reactivado'}.")
        elif accion == "eliminar":
            services.eliminar_item(request.user, tipo, _item_del_menu(menu, tipo, item_id).pk)
        else:
            messages.error(request, "Acción no reconocida.")
    except services.ErrorMenu as error:
        messages.error(request, error.mensaje)
    return _volver(menu)


def _item_del_menu(menu, tipo, item_id):
    if tipo == "acompanamiento":
        return get_object_or_404(Acompanamiento, pk=item_id, plato__menu=menu)
    return get_object_or_404(PlatoDia, pk=item_id, menu=menu)


@user_passes_test(es_administrador, login_url="login")
def disponibilidad_admin(request, menu_id):
    menu = get_object_or_404(MenuDia, pk=menu_id)
    return respuesta_json_con_etag(request, services.disponibilidad(menu))


@user_passes_test(operador_o_administrador, login_url="login")
def disponibilidad_hoy(request):
    """Polling del escáner cada 3 s: menú publicado de hoy en el local de quien consulta."""
    menu = services.menu_publicado_de_usuario(request.user)
    if menu is None:
        return respuesta_json_con_etag(request, {"menu_id": None, "tiempos": []})
    token = request.GET.get("token") or None
    try:
        token = uuid.UUID(token) if token else None
    except ValueError:
        token = None
    return respuesta_json_con_etag(request, services.disponibilidad(menu, token=token))


@user_passes_test(es_administrador, login_url="login")
def informe_cierre(request, menu_id):
    menu = get_object_or_404(MenuDia, pk=menu_id)
    return render(
        request,
        "menus/cierre.html",
        {"menu": menu, "filas": services.informe_cierre(menu), "volver": _menu_url(menu)},
    )


# --- Tiempos ---------------------------------------------------------------------------

@user_passes_test(es_administrador, login_url="login")
def tiempos(request):
    tiempo = None
    if request.GET.get("editar", "").isdigit():
        tiempo = TiempoMenu.objects.filter(pk=int(request.GET["editar"])).first()
    form = TiempoForm(request.POST or None, instance=tiempo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tiempo guardado.")
        return redirect("menus:tiempos")
    return render(
        request,
        "menus/tiempos.html",
        {"tiempos": TiempoMenu.objects.all(), "form": form, "editando": tiempo},
    )
