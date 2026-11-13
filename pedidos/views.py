from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from consumos.services import PedidoRechazado
from locales.models import Local
from menus.models import PlatoDia
from operadores.models import local_de_usuario

from .models import Pedido, PedidoItem
from .services import cambiar_plato


def es_administrador(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(es_administrador, login_url="login")
def pedidos_del_dia(request):
    locales = Local.objects.filter(activo=True)
    local = None
    if request.GET.get("local", "").isdigit():
        local = Local.objects.filter(pk=int(request.GET["local"])).first()
    local = local or local_de_usuario(request.user) or locales.first()
    fecha = parse_date(request.GET.get("fecha", "") or "") or timezone.localdate()

    pedidos = (
        Pedido.objects.filter(local=local, fecha=fecha)
        .select_related("consumo__trabajador__empresa", "consumo__operador", "consumo__anulado_por")
        .prefetch_related("items__plato__acompanamientos")
        .order_by("-folio")
    )
    # Opciones de cambio por tiempo: cada plato del mismo tiempo, con cada acompañamiento si tiene.
    opciones_por_tiempo = {}
    for plato in PlatoDia.objects.filter(menu__local=local, menu__fecha=fecha).prefetch_related("acompanamientos"):
        acomps = list(plato.acompanamientos.all())
        lista = opciones_por_tiempo.setdefault(plato.tiempo_id, [])
        if acomps:
            lista.extend((f"{plato.pk}:{a.pk}", f"{plato.nombre} + {a.nombre}") for a in acomps)
        else:
            lista.append((f"{plato.pk}:", plato.nombre))
    filas = []
    for pedido in pedidos:
        items = []
        for item in pedido.items.all():
            actual = f"{item.plato_id}:{item.acompanamiento_id or ''}"
            items.append({"item": item, "actual": actual, "opciones": opciones_por_tiempo.get(item.plato.tiempo_id, [])})
        filas.append({"pedido": pedido, "items": items})
    return render(
        request,
        "pedidos/lista.html",
        {
            "locales": locales,
            "local": local,
            "fecha": fecha,
            "filas": filas,
            "vigentes": sum(1 for f in filas if f["pedido"].estado != Pedido.ANULADO),
            "anulados": sum(1 for f in filas if f["pedido"].estado == Pedido.ANULADO),
        },
    )


@user_passes_test(es_administrador, login_url="login")
@require_POST
def cambiar_item(request, item_id):
    plato_id, _, acomp_id = request.POST.get("opcion", "").partition(":")
    item = PedidoItem.objects.select_related("pedido").filter(pk=item_id).first()
    if item is None:
        messages.error(request, "La línea del pedido no existe.")
        return redirect("pedidos:lista")
    try:
        cambiar_plato(item.pk, plato_id, acomp_id or None, request.user, request.POST.get("motivo", ""))
    except PedidoRechazado as rechazo:
        messages.error(request, rechazo.mensaje)
    else:
        messages.success(request, f"Pedido {item.pedido.folio_texto}: plato cambiado.")
    return redirect(_volver(request, item.pedido))


def _volver(request, pedido):
    destino = request.POST.get("volver", "")
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return destino
    return f"/pedidos/?local={pedido.local_id}&fecha={pedido.fecha:%Y-%m-%d}"
