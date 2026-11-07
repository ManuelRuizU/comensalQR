from django.contrib import admin

from .models import Local


@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "direccion", "telefono", "activo", "creado_en")
    list_filter = ("activo",)
    search_fields = ("nombre", "direccion", "telefono")
