from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from empresas.models import Empresa
from .forms import TrabajadorForm
from .models import Trabajador


def es_administrador(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(es_administrador, login_url="login")
def lista_trabajadores(request):
    trabajadores = Trabajador.objects.select_related("empresa")
    return render(
        request,
        "trabajadores/lista.html",
        {"trabajadores": trabajadores, "empresa": None},
    )


@user_passes_test(es_administrador, login_url="login")
def lista_trabajadores_empresa(request, empresa_id):
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    trabajadores = Trabajador.objects.filter(empresa=empresa).select_related("empresa")
    return render(
        request,
        "trabajadores/lista.html",
        {"trabajadores": trabajadores, "empresa": empresa},
    )


@user_passes_test(es_administrador, login_url="login")
def crear_trabajador(request):
    form = TrabajadorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("trabajadores:lista")
    return render(request, "trabajadores/formulario.html", {"form": form})


@user_passes_test(es_administrador, login_url="login")
def descargar_qr(request, trabajador_id):
    trabajador = get_object_or_404(Trabajador, pk=trabajador_id)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=4,
    )
    qr.add_data(str(trabajador.token_qr))
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="#17232c", back_color="#ffffff").convert("RGB")
    tarjeta = Image.new("RGB", (1000, 1220), "#f4f7f6")
    dibujo = ImageDraw.Draw(tarjeta)

    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    bold_font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    regular = ImageFont.truetype(font_path, 34) if font_path.exists() else ImageFont.load_default()
    bold = ImageFont.truetype(bold_font_path, 48) if bold_font_path.exists() else regular
    small = ImageFont.truetype(font_path, 26) if font_path.exists() else ImageFont.load_default()

    dibujo.rounded_rectangle((45, 45, 955, 1175), radius=28, fill="#ffffff", outline="#dce6e3", width=4)
    dibujo.text((85, 85), "COMENSALQR", fill="#087f73", font=bold)
    dibujo.text((85, 175), trabajador.nombre + " " + trabajador.apellido, fill="#17232c", font=bold)
    dibujo.text((85, 245), trabajador.empresa.nombre, fill="#687782", font=regular)

    qr_size = 720
    qr_image = qr_image.resize((qr_size, qr_size))
    tarjeta.paste(qr_image, ((1000 - qr_size) // 2, 330))
    dibujo.text((85, 1090), "Presentar este código para registrar el almuerzo", fill="#687782", font=small)

    contenido = BytesIO()
    tarjeta.save(contenido, format="PNG")
    contenido.seek(0)
    response = HttpResponse(contenido.getvalue(), content_type="image/png")
    nombre_archivo = slugify(f"qr-{trabajador.empresa.nombre}-{trabajador.nombre}-{trabajador.apellido}")
    response["Content-Disposition"] = (
        f'attachment; filename="{nombre_archivo}.png"'
    )
    return response


@user_passes_test(es_administrador, login_url="login")
def eliminar_trabajadores(request, empresa_id):
    if request.method != "POST":
        return redirect("trabajadores:por_empresa", empresa_id=empresa_id)

    empresa = get_object_or_404(Empresa, pk=empresa_id)
    trabajador_ids = request.POST.getlist("trabajadores")
    trabajadores = Trabajador.objects.filter(
        empresa=empresa,
        pk__in=trabajador_ids,
    )

    if not trabajador_ids:
        messages.warning(request, "Selecciona al menos un trabajador para eliminar.")
        return redirect("trabajadores:por_empresa", empresa_id=empresa.pk)

    eliminados = 0
    try:
        with transaction.atomic():
            for trabajador in trabajadores:
                trabajador.delete()
                eliminados += 1
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar un trabajador que tiene consumos registrados.",
        )
    else:
        messages.success(
            request,
            f"{eliminados} trabajador(es) eliminado(s) correctamente.",
        )

    return redirect("trabajadores:por_empresa", empresa_id=empresa.pk)
