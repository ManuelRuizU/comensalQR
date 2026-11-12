import uuid

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.cache import never_cache

from .forms import OperadorEditarForm, OperadorForm
from .models import Operador
from .access_control import (
    MENSAJE_LOGIN_INVALIDO,
    limpiar_fallos_cuenta,
    reservar_intento,
    registrar_fallo,
)


def es_administrador(user):
    return user.is_authenticated and user.is_staff


def ingreso(request):
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if request.user.is_authenticated:
        destino = _destino_usuario(request.user)
        if destino:
            return redirect(_destino_post_login(request, request.user, next_url, destino))
        logout(request)
        messages.error(request, MENSAJE_LOGIN_INVALIDO)

    username = request.POST.get("username", "") if request.method == "POST" else ""
    if request.method == "POST" and not reservar_intento(request, username):
        messages.error(request, MENSAJE_LOGIN_INVALIDO)
        form = AuthenticationForm(request)
    else:
        form = AuthenticationForm(request, data=request.POST or None)
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
