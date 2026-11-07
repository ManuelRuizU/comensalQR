import uuid

from django.contrib.auth.decorators import user_passes_test
from django.db import IntegrityError, transaction
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from empresas.models import Empresa
from trabajadores.models import Trabajador

from .models import Consumo


def operador_o_administrador(user):
    perfil = getattr(user, "perfil_operador", None)
    return user.is_authenticated and (user.is_staff or (perfil and perfil.activo))


@user_passes_test(lambda user: user.is_authenticated and user.is_staff, login_url="login")
def dashboard(request):
    hoy = timezone.localdate()
    consumos_hoy = Consumo.objects.filter(fecha=hoy)
    empresas = (
        consumos_hoy.values("trabajador__empresa__nombre")
        .annotate(total=Count("id"))
        .order_by("trabajador__empresa__nombre")
    )
    contexto = {
        "fecha": hoy,
        "total_hoy": consumos_hoy.count(),
        "empresas": empresas,
        "ultimos_consumos": consumos_hoy.select_related(
            "trabajador", "trabajador__empresa"
        )[:10],
    }
    return render(request, "consumos/dashboard.html", contexto)


@user_passes_test(operador_o_administrador, login_url="login")
def historial(request):
    consumos = Consumo.objects.select_related(
        "trabajador", "trabajador__empresa", "operador"
    )

    fecha = parse_date(request.GET.get("fecha", "") or "")
    empresa_id = request.GET.get("empresa", "")
    trabajador_id = request.GET.get("trabajador", "")

    if fecha:
        consumos = consumos.filter(fecha=fecha)
    if empresa_id.isdigit():
        consumos = consumos.filter(trabajador__empresa_id=int(empresa_id))
    if trabajador_id.isdigit():
        consumos = consumos.filter(trabajador_id=int(trabajador_id))

    pagina = Paginator(consumos, 50).get_page(request.GET.get("pagina"))
    contexto = {
        "consumos": pagina,
        "empresas": Empresa.objects.filter(activa=True),
        "trabajadores": Trabajador.objects.select_related("empresa").filter(activo=True),
        "fecha_seleccionada": fecha,
        "empresa_seleccionada": empresa_id,
        "trabajador_seleccionado": trabajador_id,
    }
    return render(request, "consumos/historial.html", contexto)


@user_passes_test(operador_o_administrador, login_url="login")
def escaner(request):
    trabajador = None
    consumo_existente = None
    error = None
    exito = False
    hoy = timezone.localdate()

    if request.method == "POST":
        token = request.POST.get("token", "").strip()
        try:
            token_qr = uuid.UUID(token)
        except ValueError:
            error = "QR no válido."
        else:
            trabajador = (
                Trabajador.objects.select_related("empresa")
                .filter(token_qr=token_qr, activo=True, empresa__activa=True)
                .first()
            )
            if trabajador is None:
                error = "No se encontro un trabajador activo para este codigo."
            else:
                consumo_existente = Consumo.objects.filter(
                    trabajador=trabajador, fecha=hoy
                ).first()
                if consumo_existente is None:
                    try:
                        with transaction.atomic():
                            Consumo.objects.create(
                                trabajador=trabajador,
                                fecha=hoy,
                                operador=request.user,
                            )
                        exito = True
                    except IntegrityError:
                        consumo_existente = Consumo.objects.get(
                            trabajador=trabajador, fecha=hoy
                        )

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            if error:
                return JsonResponse({"ok": False, "message": error}, status=400)
            if exito:
                return JsonResponse({
                    "ok": True,
                    "status": "registered",
                    "message": "Almuerzo registrado.",
                    "worker": str(trabajador),
                    "company": str(trabajador.empresa),
                })
            return JsonResponse({
                "ok": True,
                "status": "duplicate",
                "message": "Almuerzo ya registrado.",
                "worker": str(trabajador),
                "company": str(trabajador.empresa),
                "time": consumo_existente.registrado_en.strftime("%H:%M"),
            })

    return render(
        request,
        "consumos/escaner.html",
        {
            "trabajador": trabajador,
            "consumo_existente": consumo_existente,
            "error": error,
            "exito": exito,
        },
    )
