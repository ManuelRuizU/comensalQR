from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from .forms import EmpresaForm
from .models import Empresa


def es_administrador(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(es_administrador, login_url="login")
def lista_empresas(request):
    empresas = Empresa.objects.all()
    return render(request, "empresas/lista.html", {"empresas": empresas})


@user_passes_test(es_administrador, login_url="login")
def crear_empresa(request):
    form = EmpresaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("empresas:lista")
    return render(request, "empresas/formulario.html", {"form": form})


@user_passes_test(es_administrador, login_url="login")
def perfil_empresa(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    return render(request, "empresas/perfil.html", {"empresa": empresa})


@user_passes_test(es_administrador, login_url="login")
def editar_empresa(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    form = EmpresaForm(request.POST or None, instance=empresa)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("empresas:editar", pk=empresa.pk)
    return render(
        request,
        "empresas/editar.html",
        {"empresa": empresa, "form": form},
    )


@user_passes_test(es_administrador, login_url="login")
def eliminar_empresas(request):
    if request.method != "POST":
        return redirect("empresas:lista")

    empresa_ids = request.POST.getlist("empresas")
    if not empresa_ids:
        messages.warning(request, "Selecciona al menos una empresa para eliminar.")
        return redirect("empresas:lista")

    empresas = Empresa.objects.filter(pk__in=empresa_ids)
    eliminadas = 0
    try:
        with transaction.atomic():
            for empresa in empresas:
                empresa.delete()
                eliminadas += 1
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar una empresa que tiene trabajadores registrados.",
        )
    else:
        messages.success(
            request,
            f"{eliminadas} empresa(s) eliminada(s) correctamente.",
        )

    return redirect("empresas:lista")
