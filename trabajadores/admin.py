from django.contrib import admin

from .models import Trabajador


@admin.register(Trabajador)
class TrabajadorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "apellido", "rut", "empresa", "activo")
    list_filter = ("activo", "empresa")
    search_fields = ("nombre", "apellido", "rut")
    readonly_fields = ("token_qr",)
