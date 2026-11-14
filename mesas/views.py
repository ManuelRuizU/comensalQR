from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from locales.models import Local
from operadores.models import local_de_usuario

from . import services, tarjetas
from .models import Mesa


def es_administrador(user):
    return user.is_authenticated and user.is_staff


def _local_elegido(request, valor):
    local = Local.objects.filter(pk=int(valor)).first() if str(valor).isdigit() else None
    return local or local_de_usuario(request.user) or Local.objects.filter(activo=True).first()


def _volver(local):
    return redirect(f"{reverse('mesas:lista')}?local={local.pk}")


@user_passes_test(es_administrador, login_url="login")
def lista(request):
    local = _local_elegido(request, request.GET.get("local", ""))
    mesas = Mesa.objects.filter(local=local).order_by("-activa", "nombre") if local else Mesa.objects.none()
    return render(
        request,
        "mesas/lista.html",
        {"locales": Local.objects.filter(activo=True), "local": local, "mesas": mesas},
    )


@user_passes_test(es_administrador, login_url="login")
@require_POST
def crear(request):
    local = get_object_or_404(Local, pk=request.POST.get("local"))
    try:
        mesa = services.crear_mesa(request.user, local, request.POST.get("nombre"))
    except services.MesaInvalida as error:
        messages.error(request, error.mensaje)
    else:
        messages.success(request, f"{mesa.nombre} creada. Descarga su QR para imprimirlo.")
    return _volver(local)


@user_passes_test(es_administrador, login_url="login")
@require_POST
def cambiar_estado(request, mesa_id):
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    activa = request.POST.get("accion") == "reactivar"
    services.cambiar_estado(request.user, mesa, activa)
    if activa:
        messages.success(request, f"{mesa.nombre} reactivada: su QR vuelve a funcionar.")
    else:
        messages.warning(request, f"{mesa.nombre} desactivada: su QR ya no se acepta en el escáner.")
    return _volver(mesa.local)


@user_passes_test(es_administrador, login_url="login")
def pdf_qr(request):
    """PDF A4 con los QR de las mesas activas del local (o solo las seleccionadas)."""
    local = _local_elegido(request, request.GET.get("local", ""))
    mesas = Mesa.objects.filter(local=local, activa=True).select_related("local")
    seleccion = [valor for valor in request.GET.getlist("mesas") if valor.isdigit()]
    if seleccion:
        mesas = mesas.filter(pk__in=seleccion)
    if not mesas.exists():
        messages.warning(request, "No hay mesas activas para imprimir.")
        return _volver(local)
    respuesta = HttpResponse(tarjetas.pdf_mesas(mesas), content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="{slugify(f"qr-mesas-{local.nombre}")}.pdf"'
    respuesta["Cache-Control"] = "no-store"
    return respuesta
