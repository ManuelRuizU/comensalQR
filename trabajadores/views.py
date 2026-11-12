import uuid
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.cache import never_cache

from empresas.models import Empresa
from .forms import TrabajadorForm
from . import importacion, tarjetas
from .models import TokenQRReservado, Trabajador


def es_administrador(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(es_administrador, login_url="login")
def lista_trabajadores(request):
    trabajadores = _trabajadores_filtrados(request).select_related("empresa")
    return render(
        request,
        "trabajadores/lista.html",
        {"trabajadores": trabajadores, "empresa": None, "ver_eliminados": request.GET.get("estado") == "eliminados"},
    )


@user_passes_test(es_administrador, login_url="login")
def lista_trabajadores_empresa(request, empresa_id):
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    trabajadores = _trabajadores_filtrados(request).filter(empresa=empresa).select_related("empresa")
    return render(
        request,
        "trabajadores/lista.html",
        {"trabajadores": trabajadores, "empresa": empresa, "ver_eliminados": request.GET.get("estado") == "eliminados"},
    )


def _trabajadores_filtrados(request):
    if request.GET.get("estado") == "eliminados":
        return Trabajador.objects.filter(eliminado_en__isnull=False)
    return Trabajador.objects.filter(eliminado_en__isnull=True)


@user_passes_test(es_administrador, login_url="login")
def crear_trabajador(request):
    form = TrabajadorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("trabajadores:lista")
    return render(request, "trabajadores/formulario.html", {"form": form})


@user_passes_test(es_administrador, login_url="login")
def editar_trabajador(request, trabajador_id):
    # Un trabajador eliminado no se edita: su registro queda como respaldo histórico.
    trabajador = get_object_or_404(Trabajador, pk=trabajador_id, eliminado_en__isnull=True)
    form = TrabajadorForm(request.POST or None, instance=trabajador)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Trabajador {trabajador} actualizado correctamente.")
        return redirect("trabajadores:por_empresa", empresa_id=trabajador.empresa_id)
    return render(request, "trabajadores/formulario.html", {"form": form, "trabajador": trabajador})


def _respuesta_archivo(contenido, tipo, nombre_archivo):
    response = HttpResponse(contenido, content_type=tipo)
    response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    response["Cache-Control"] = "no-store"
    return response


@user_passes_test(es_administrador, login_url="login")
def descargar_qr(request, trabajador_id):
    trabajador = get_object_or_404(
        Trabajador.objects.select_related("empresa"), pk=trabajador_id, eliminado_en__isnull=True
    )
    nombre_archivo = slugify(f"qr-{trabajador.empresa.nombre}-{trabajador.nombre}-{trabajador.apellido}")
    return _respuesta_archivo(
        tarjetas.png_bytes(tarjetas.tarjeta_impresa(trabajador)), "image/png", f"{nombre_archivo}.png"
    )


@user_passes_test(es_administrador, login_url="login")
def descargar_qr_telefono(request, trabajador_id):
    trabajador = get_object_or_404(
        Trabajador.objects.select_related("empresa"), pk=trabajador_id, eliminado_en__isnull=True
    )
    return _respuesta_archivo(
        tarjetas.png_bytes(tarjetas.tarjeta_telefono(trabajador)),
        "image/png",
        f"{tarjetas.nombre_archivo_trabajador(trabajador)}.png",
    )


def _trabajadores_para_descarga(request, empresa):
    """Trabajadores vigentes y activos de la empresa; opcionalmente solo los seleccionados."""
    trabajadores = Trabajador.objects.filter(
        empresa=empresa, activo=True, eliminado_en__isnull=True
    ).select_related("empresa")
    seleccionados = [valor for valor in request.GET.getlist("trabajadores") if valor.isdigit()]
    if seleccionados:
        trabajadores = trabajadores.filter(pk__in=seleccionados)
    return list(trabajadores)


@user_passes_test(es_administrador, login_url="login")
def descargar_qr_pdf(request, empresa_id):
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    trabajadores = _trabajadores_para_descarga(request, empresa)
    if not trabajadores:
        messages.warning(request, "No hay trabajadores activos para generar tarjetas.")
        return redirect("trabajadores:por_empresa", empresa_id=empresa.pk)
    nombre = slugify(f"qr-imprimir-{empresa.nombre}-{timezone.localdate():%Y-%m-%d}")
    return _respuesta_archivo(tarjetas.pdf_imprimible(trabajadores), "application/pdf", f"{nombre}.pdf")


@user_passes_test(es_administrador, login_url="login")
def descargar_qr_zip(request, empresa_id):
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    trabajadores = _trabajadores_para_descarga(request, empresa)
    if not trabajadores:
        messages.warning(request, "No hay trabajadores activos para generar imágenes.")
        return redirect("trabajadores:por_empresa", empresa_id=empresa.pk)
    nombre = slugify(f"qr-telefono-{empresa.nombre}-{timezone.localdate():%Y-%m-%d}")
    return _respuesta_archivo(tarjetas.zip_telefono(trabajadores), "application/zip", f"{nombre}.zip")


@user_passes_test(es_administrador, login_url="login")
def plantilla_importacion(request):
    return _respuesta_archivo(
        importacion.plantilla_xlsx(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "plantilla-trabajadores-comensalqr.xlsx",
    )


_SESION_IMPORTACION = "importacion_trabajadores"


@user_passes_test(es_administrador, login_url="login")
@never_cache
def importar_trabajadores(request, empresa_id):
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    if not empresa.activa:
        messages.error(request, "No se pueden importar trabajadores a una empresa inactiva.")
        return redirect("trabajadores:por_empresa", empresa_id=empresa.pk)

    if request.method == "POST" and request.POST.get("accion") == "confirmar":
        return _confirmar_importacion(request, empresa)

    filas = None
    error = None
    token = None
    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        if archivo is None:
            error = "Selecciona un archivo .xlsx o .csv."
        else:
            try:
                filas = importacion.validar_filas(importacion.leer_archivo(archivo), empresa)
            except importacion.ArchivoInvalido as excepcion:
                error = str(excepcion)
        if filas and all(fila.valida for fila in filas):
            token = uuid.uuid4().hex
            request.session[_SESION_IMPORTACION] = {
                "token": token,
                "empresa_id": empresa.pk,
                "filas": [fila.como_dict() for fila in filas],
            }
    return render(
        request,
        "trabajadores/importar.html",
        {
            "empresa": empresa,
            "filas": filas,
            "error": error,
            "token": token,
            "validas": sum(1 for fila in filas if fila.valida) if filas else 0,
            "con_errores": sum(1 for fila in filas if not fila.valida) if filas else 0,
        },
    )


def _confirmar_importacion(request, empresa):
    datos = request.session.get(_SESION_IMPORTACION)
    if (
        not datos
        or datos.get("token") != request.POST.get("token")
        or datos.get("empresa_id") != empresa.pk
    ):
        messages.warning(request, "La importación expiró o ya fue procesada. Sube el archivo nuevamente.")
        return redirect("trabajadores:importar", empresa_id=empresa.pk)
    del request.session[_SESION_IMPORTACION]

    try:
        with transaction.atomic():
            # Bloquea la empresa para que dos importaciones simultáneas no dupliquen RUT.
            Empresa.objects.select_for_update().get(pk=empresa.pk)
            creados = []
            for fila in datos["filas"]:
                trabajador = Trabajador(empresa=empresa, **fila)
                trabajador.full_clean()
                trabajador.save()
                creados.append(trabajador)
    except ValidationError:
        messages.error(
            request,
            "Algunos trabajadores cambiaron mientras revisabas la vista previa. Sube el archivo nuevamente.",
        )
        return redirect("trabajadores:importar", empresa_id=empresa.pk)

    ids = [trabajador.pk for trabajador in creados]
    consulta = urlencode([("trabajadores", pk) for pk in ids])
    return render(
        request,
        "trabajadores/importacion_resultado.html",
        {"empresa": empresa, "creados": creados, "consulta": consulta},
    )


@user_passes_test(es_administrador, login_url="login")
def regenerar_qr(request, trabajador_id):
    if request.method != "POST":
        return redirect("trabajadores:lista")

    with transaction.atomic():
        trabajador = get_object_or_404(
            Trabajador.objects.select_for_update(),
            pk=trabajador_id,
            activo=True,
            eliminado_en__isnull=True,
        )
        token_anterior = trabajador.token_qr
        TokenQRReservado.objects.create(
            token=token_anterior,
            trabajador=trabajador,
            invalidado_en=timezone.now(),
            invalidado_por=request.user,
        )

        while True:
            token_nuevo = uuid.uuid4()
            if (
                not Trabajador.objects.filter(token_qr=token_nuevo).exists()
                and not TokenQRReservado.objects.filter(token=token_nuevo).exists()
            ):
                break
        trabajador.token_qr = token_nuevo
        trabajador.save(update_fields=["token_qr"])

    messages.success(request, "QR regenerado. El token anterior quedó invalidado.")
    return redirect("trabajadores:por_empresa", empresa_id=trabajador.empresa_id)


@user_passes_test(es_administrador, login_url="login")
def eliminar_trabajadores(request, empresa_id):
    if request.method != "POST":
        return redirect("trabajadores:por_empresa", empresa_id=empresa_id)

    empresa = get_object_or_404(Empresa, pk=empresa_id)
    trabajador_ids = [
        value for value in request.POST.getlist("trabajadores") if value.isdigit()
    ]
    trabajadores = Trabajador.objects.filter(empresa=empresa, pk__in=trabajador_ids, eliminado_en__isnull=True)

    if not trabajador_ids:
        messages.warning(request, "Selecciona al menos un trabajador para eliminar.")
        return redirect("trabajadores:por_empresa", empresa_id=empresa.pk)

    eliminados = 0
    with transaction.atomic():
        ahora = timezone.now()
        for trabajador in trabajadores.select_for_update():
            trabajador.activo = False
            trabajador.eliminado_en = ahora
            trabajador.eliminado_por = request.user
            trabajador.save(update_fields=["activo", "eliminado_en", "eliminado_por"])
            eliminados += 1
    if eliminados:
        messages.success(request, f"{eliminados} trabajador(es) eliminado(s) correctamente.")
    else:
        messages.warning(request, "No se seleccionaron trabajadores activos para eliminar.")

    return redirect("trabajadores:por_empresa", empresa_id=empresa.pk)
