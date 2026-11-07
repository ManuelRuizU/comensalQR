from django.contrib import admin

from .models import Empresa


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "rut", "telefono", "activa", "creada_en")
    list_filter = ("activa",)
    search_fields = ("nombre", "rut", "encargado_personal", "encargado_pagos")
