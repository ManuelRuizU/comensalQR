import uuid

from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from empresas.models import Empresa
from empresas.validators import normalizar_rut
from locales.models import Local
from operadores.models import local_de_usuario
from trabajadores.models import Trabajador

from .models import Consumo
from .services import TrabajadorNoDisponible, registrar_consumo_diario


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
        "trabajador", "trabajador__empresa", "operador", "local"
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
    filtros = request.GET.copy()
    filtros.pop("pagina", None)
    contexto = {
        "consumos": pagina,
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
        }
        for consumo in Consumo.objects.filter(operador=usuario, fecha=fecha)
        .select_related("trabajador", "trabajador__empresa")
        .order_by("-registrado_en")[:limite]
    ]


@user_passes_test(operador_o_administrador, login_url="login")
def escaner(request):
    hoy = timezone.localdate()

    if request.method != "POST":
        return render(
            request,
            "consumos/escaner.html",
            {
                "total_hoy": Consumo.objects.filter(fecha=hoy).count(),
                "ultimos": _ultimos_del_operador(request.user, hoy),
                "local": local_de_usuario(request.user),
            },
        )

    trabajador = None
    resultado = None
    error = None
    metodo = Consumo.METODO_QR
    trabajador_id = request.POST.get("trabajador_id", "").strip()
    if trabajador_id:
        # Registro manual: el operador eligió al trabajador tras buscarlo por RUT.
        metodo = Consumo.METODO_RUT
        if trabajador_id.isdigit():
            trabajador = Trabajador.objects.select_related("empresa").filter(pk=int(trabajador_id)).first()
        if trabajador is None:
            error = "Trabajador no encontrado."
    else:
        token = request.POST.get("token", "").strip()
        try:
            token_qr = uuid.UUID(token)
        except ValueError:
            error = "QR no válido."
        else:
            trabajador = Trabajador.objects.select_related("empresa").filter(token_qr=token_qr).first()
            if trabajador is None:
                error = "QR no válido o dado de baja."

    if trabajador is not None:
        try:
            resultado = registrar_consumo_diario(trabajador.pk, request.user, fecha=hoy, metodo=metodo)
        except TrabajadorNoDisponible:
            error = "Trabajador inactivo o desvinculado. No puede registrar almuerzos."

    total_hoy = Consumo.objects.filter(fecha=hoy).count()
    if error:
        return JsonResponse({"ok": False, "status": "error", "message": error, "today_total": total_hoy}, status=400)

    datos = {
        "ok": True,
        "worker": str(trabajador),
        "company": str(trabajador.empresa),
        "used": resultado.usados,
        "quota": resultado.cupo,
        "number": resultado.consumo.numero,
        "manual": metodo == Consumo.METODO_RUT,
        "time": timezone.localtime(resultado.consumo.registrado_en).strftime("%H:%M"),
        "today_total": total_hoy,
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
        usados = Consumo.objects.filter(trabajador=trabajador, fecha=hoy).count()
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
