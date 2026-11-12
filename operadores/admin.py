from django.contrib import admin

from .models import Administrador, Operador


@admin.register(Administrador)
class AdministradorAdmin(admin.ModelAdmin):
    list_display = ("__str__", "usuario", "local", "creado_en")
    list_filter = ("local",)
    search_fields = ("usuario__first_name", "usuario__last_name", "usuario__email")


@admin.register(Operador)
class OperadorAdmin(admin.ModelAdmin):
    list_display = ("__str__", "usuario", "local", "activo", "creado_en")
    list_filter = ("activo", "local")
    search_fields = ("usuario__first_name", "usuario__last_name", "usuario__username")