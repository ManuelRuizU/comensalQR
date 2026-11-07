from django.contrib.auth import login
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.utils.text import slugify

from .forms import OperadorForm
from .models import Operador


def es_administrador(user):
    return user.is_authenticated and user.is_staff


def ingreso(request):
    if request.user.is_authenticated:
        return redirect("consumos:dashboard" if request.user.is_staff else "consumos:escaner")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.get_user()
        login(request, usuario)
        return redirect("consumos:dashboard" if usuario.is_staff else "consumos:escaner")
    return render(request, "registration/login.html", {"form": form})


@user_passes_test(es_administrador, login_url="login")
def lista_operadores(request):
    operadores = Operador.objects.select_related("usuario")
    return render(request, "operadores/lista.html", {"operadores": operadores})


@user_passes_test(es_administrador, login_url="login")
def crear_operador(request):
    form = OperadorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        nombre = form.cleaned_data["nombre"].strip()
        apellido = form.cleaned_data["apellido"].strip()
        clave = form.cleaned_data["clave"]
        usuario_base = f"{slugify(nombre)}.{slugify(apellido)}"
        usuario_nombre = usuario_base
        sufijo = 2
        while User.objects.filter(username=usuario_nombre).exists():
            usuario_nombre = f"{usuario_base}{sufijo}"
            sufijo += 1
        usuario = User.objects.create_user(
            username=usuario_nombre,
            first_name=nombre,
            last_name=apellido,
            password=clave,
        )
        operador = Operador.objects.create(usuario=usuario)
        return render(
            request,
            "operadores/credenciales.html",
            {"operador": operador, "clave": clave},
        )
    return render(request, "operadores/formulario.html", {"form": form})
