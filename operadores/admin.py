from django.contrib import admin

from .models import Operador


@admin.register(Operador)
class OperadorAdmin(admin.ModelAdmin):
    list_display = ("__str__", "usuario", "activo", "creado_en")
    list_filter = ("activo",)
    search_fields = ("usuario__first_name", "usuario__last_name", "usuario__username")