import uuid

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.cache import never_cache

from locales.forms import LocalForm

from .forms import (
    AdministradorEditarForm,
    AdministradorForm,
    OperadorEditarForm,
    OperadorForm,
    normalizar_correo,
)
from .models import Administrador, Operador
from .access_control import (
    MENSAJE_LOGIN_INVALIDO,
    limpiar_fallos_cuenta,
    reservar_intento,
    registrar_fallo,
)


def es_administrador(user):
    return user.is_authenticated and user.is_staff


def hay_administradores():
    return User.objects.filter(is_staff=True).exists()


def ingreso(request):
    if request.method == "GET" and not hay_administradores():
        # Instalación nueva: primero hay que registrar el restaurante y su administrador.
        return redirect("registro_inicial")

    next_url = request.POST.get("next") or request.GET.get("next", "")
    if request.user.is_authenticated:
        destino = _destino_usuario(request.user)
        if destino:
            return redirect(_destino_post_login(request, request.user, next_url, destino))
        logout(request)
        messages.error(request, MENSAJE_LOGIN_INVALIDO)

    datos = None
    username = ""
    if request.method == "POST":
        datos = request.POST.copy()
        username = datos.get("username", "").strip()
        if "@" in username:
            # Los administradores ingresan con su correo, que se guarda en minúsculas.
            username = normalizar_correo(username)
        datos["username"] = username
    if request.method == "POST" and not reservar_intento(request, username):
        messages.error(request, MENSAJE_LOGIN_INVALIDO)
        form = AuthenticationForm(request)
    else:
        form = AuthenticationForm(request, data=datos)
        if request.method == "POST" and form.is_valid():
            usuario = form.get_user()
            destino = _destino_usuario(usuario)
            if destino:
                limpiar_fallos_cuenta(request, username)
                login(request, usuario)
                return redirect(_destino_post_login(request, usuario, next_url, destino))
            registrar_fallo(request, username)
            messages.error(request, MENSAJE_LOGIN_INVALIDO)
        elif request.method == "POST":
            registrar_fallo(request, username)
    return render(
        request,
        "registration/login.html",
        {"form": form, "next": next_url},
    )


def _destino_post_login(request, usuario, next_url, destino):
    if usuario.is_staff and next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return destino


def _destino_usuario(usuario):
    if usuario.is_staff:
        return "consumos:dashboard"
    perfil = getattr(usuario, "perfil_operador", None)
    if perfil and perfil.activo:
        return "consumos:escaner"
    return None


@user_passes_test(es_administrador, login_url="login")
def lista_operadores(request):
    operadores = Operador.objects.select_related("usuario", "local")
    return render(request, "operadores/lista.html", {"operadores": operadores})


@user_passes_test(es_administrador, login_url="login")
@never_cache
def crear_operador(request):
    if request.method == "POST":
        form = OperadorForm(request.POST)
    else:
        solicitud_id = uuid.uuid4().hex
        solicitudes = request.session.get("solicitudes_crear_operador", [])
        solicitudes.append(solicitud_id)
        request.session["solicitudes_crear_operador"] = solicitudes[-5:]
        form = OperadorForm(initial={"solicitud_id": solicitud_id})

    if request.method == "POST" and form.is_valid():
        solicitud_id = form.cleaned_data["solicitud_id"]
        solicitudes = request.session.get("solicitudes_crear_operador", [])
        if solicitud_id not in solicitudes:
            messages.info(request, "Este formulario ya fue procesado.")
            return redirect("operadores:lista")
        solicitudes.remove(solicitud_id)
        request.session["solicitudes_crear_operador"] = solicitudes

        nombre = form.cleaned_data["nombre"].strip()
        apellido = form.cleaned_data["apellido"].strip()
        clave = form.cleaned_data["clave"]
        usuario_base = f"{slugify(nombre)}.{slugify(apellido)}"[:145]
        sufijo = 1
        with transaction.atomic():
            while True:
                usuario_nombre = usuario_base if sufijo == 1 else f"{usuario_base}{sufijo}"
                try:
                    with transaction.atomic():
                        usuario = User.objects.create_user(
                            username=usuario_nombre,
                            first_name=nombre,
                            last_name=apellido,
                            password=clave,
                        )
                    break
                except IntegrityError:
                    if not User.objects.filter(username=usuario_nombre).exists():
                        raise
                    sufijo += 1
            operador = Operador.objects.create(usuario=usuario, local=form.cleaned_data["local"])
        return render(
            request,
            "operadores/credenciales.html",
            {"operador": operador, "clave": clave},
        )
    return render(request, "operadores/formulario.html", {"form": form})


@user_passes_test(es_administrador, login_url="login")
@never_cache
def editar_operador(request, pk):
    operador = get_object_or_404(Operador.objects.select_related("usuario", "local"), pk=pk)
    form = OperadorEditarForm(
        request.POST if request.method == "POST" else None,
        initial={"activo": operador.activo, "local": operador.local_id},
        local_actual=operador.local,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            operador.activo = form.cleaned_data["activo"]
            operador.local = form.cleaned_data["local"]
            operador.save(update_fields=["activo", "local"])
            nueva_clave = form.cleaned_data["nueva_clave"]
            if nueva_clave:
                # Cambiar la clave invalida las sesiones abiertas del operador.
                operador.usuario.set_password(nueva_clave)
                operador.usuario.save(update_fields=["password"])
        if nueva_clave:
            return render(
                request,
                "operadores/credenciales.html",
                {"operador": operador, "clave": nueva_clave, "clave_actualizada": True},
            )
        estado = "activado" if operador.activo else "desactivado"
        messages.success(request, f"Operador {estado} correctamente.")
        return redirect("operadores:lista")
    return render(
        request,
        "operadores/editar.html",
        {"operador": operador, "form": form},
    )


def _crear_usuario_administrador(datos):
    return User.objects.create_user(
        username=datos["correo"],
        email=datos["correo"],
        first_name=datos["nombre"].strip(),
        last_name=datos["apellido"].strip(),
        password=datos["clave"],
        is_staff=True,
        # «Ve todo»: también puede usar el admin de Django como respaldo.
        is_superuser=True,
    )


@never_cache
def registro_inicial(request):
    """Primer paso de una instalación nueva: crea el local y su administrador."""
    if hay_administradores():
        return redirect("login")

    form_local = LocalForm(request.POST or None, prefix="local")
    form_admin = AdministradorForm(request.POST or None, prefix="admin", con_local=False)
    form_local.fields.pop("activo", None)
    if request.method == "POST" and form_local.is_valid() and form_admin.is_valid():
        with transaction.atomic():
            if hay_administradores():
                return redirect("login")
            local = form_local.save()
            usuario = _crear_usuario_administrador(form_admin.cleaned_data)
            Administrador.objects.create(usuario=usuario, local=local)
        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(
            request,
            f"Restaurante «{local}» registrado. Ahora agrega empresas, trabajadores y operadores.",
        )
        return redirect("consumos:dashboard")
    return render(
        request,
        "registration/registro_inicial.html",
        {"form_local": form_local, "form_admin": form_admin},
    )


@user_passes_test(es_administrador, login_url="login")
def lista_administradores(request):
    administradores = (
        User.objects.filter(is_staff=True)
        .select_related("perfil_administrador__local")
        .order_by("-is_active", "first_name", "last_name", "username")
    )
    return render(request, "administradores/lista.html", {"administradores": administradores})


@user_passes_test(es_administrador, login_url="login")
@never_cache
def crear_administrador(request):
    form = AdministradorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            usuario = _crear_usuario_administrador(form.cleaned_data)
            Administrador.objects.create(usuario=usuario, local=form.cleaned_data["local"])
        messages.success(request, f"Administrador creado. Ingresa con el correo {usuario.email}.")
        return redirect("administradores:lista")
    return render(request, "administradores/formulario.html", {"form": form})


@user_passes_test(es_administrador, login_url="login")
@never_cache
def editar_administrador(request, pk):
    usuario = get_object_or_404(User.objects.select_related("perfil_administrador__local"), pk=pk, is_staff=True)
    perfil = getattr(usuario, "perfil_administrador", None)
    local_actual = perfil.local if perfil else None
    form = AdministradorEditarForm(
        request.POST or None,
        usuario=usuario,
        local_actual=local_actual,
        initial={"activo": usuario.is_active, "local": local_actual.pk if local_actual else None},
    )
    if request.method == "POST" and form.is_valid():
        activo = form.cleaned_data["activo"]
        if not activo and usuario.is_active:
            if usuario == request.user:
                form.add_error("activo", "No puedes desactivar tu propia cuenta.")
            elif not User.objects.filter(is_staff=True, is_active=True).exclude(pk=usuario.pk).exists():
                form.add_error("activo", "Debe quedar al menos un administrador activo.")
    if request.method == "POST" and form.is_valid():
        nueva_clave = form.cleaned_data["nueva_clave"]
        with transaction.atomic():
            Administrador.objects.update_or_create(
                usuario=usuario, defaults={"local": form.cleaned_data["local"]}
            )
            usuario.is_active = form.cleaned_data["activo"]
            campos = ["is_active"]
            if nueva_clave:
                usuario.set_password(nueva_clave)
                campos.append("password")
            usuario.save(update_fields=campos)
        if nueva_clave and usuario == request.user:
            # Cambiar la propia clave cierra las demás sesiones, pero no la actual.
            update_session_auth_hash(request, usuario)
        messages.success(request, "Administrador actualizado correctamente.")
        return redirect("administradores:lista")
    return render(
        request,
        "administradores/formulario.html",
        {"form": form, "administrador": usuario},
    )
