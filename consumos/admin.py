from django.contrib import admin

from .models import Consumo


@admin.register(Consumo)
class ConsumoAdmin(admin.ModelAdmin):
    list_display = ("trabajador", "empresa", "local", "fecha", "numero", "registrado_en", "operador", "metodo")
    list_filter = ("fecha", "metodo", "anulado", "local", "trabajador__empresa")
    search_fields = ("trabajador__nombre", "trabajador__apellido", "trabajador__rut")
    readonly_fields = (
        "trabajador", "fecha", "numero", "operador", "local", "registrado_en", "metodo",
        "anulado", "anulado_por", "anulado_en", "motivo_anulacion",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(ordering="trabajador__empresa", description="Empresa")
    def empresa(self, obj):
        return obj.trabajador.empresa
