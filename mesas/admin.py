from django.contrib import admin

from .models import Mesa


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "local", "activa", "creada_en")
    list_filter = ("activa", "local")
    readonly_fields = ("token",)
