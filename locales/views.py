from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from .forms import LocalForm
from .models import Local


def es_administrador(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(es_administrador, login_url="login")
def lista_locales(request):
    return render(request, "locales/lista.html", {"locales": Local.objects.all()})


@user_passes_test(es_administrador, login_url="login")
def crear_local(request):
    form = LocalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Local registrado correctamente.")
        return redirect("locales:lista")
    return render(request, "locales/formulario.html", {"form": form})


@user_passes_test(es_administrador, login_url="login")
def editar_local(request, pk):
    local = get_object_or_404(Local, pk=pk)
    form = LocalForm(request.POST or None, instance=local)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Local actualizado correctamente.")
        return redirect("locales:lista")
    return render(request, "locales/formulario.html", {"form": form})


@user_passes_test(es_administrador, login_url="login")
def eliminar_locales(request):
    if request.method != "POST":
        return redirect("locales:lista")
    ids = [value for value in request.POST.getlist("locales") if value.isdigit()]
    if not ids:
        messages.warning(request, "Selecciona al menos un local para eliminar.")
        return redirect("locales:lista")
    try:
        eliminados, _ = Local.objects.filter(pk__in=ids).delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar un local con operadores asignados o consumos registrados. "
            "Puedes desactivarlo.",
        )
        return redirect("locales:lista")
    messages.success(request, f"{eliminados} local(es) eliminado(s) correctamente.")
    return redirect("locales:lista")
