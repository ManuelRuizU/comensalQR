from django.contrib import admin

from .models import Consumo


@admin.register(Consumo)
class ConsumoAdmin(admin.ModelAdmin):
    list_display = ("trabajador", "empresa", "fecha", "numero", "registrado_en", "operador", "metodo")
    list_filter = ("fecha", "metodo", "trabajador__empresa")
    search_fields = ("trabajador__nombre", "trabajador__apellido", "trabajador__rut")
    readonly_fields = ("trabajador", "fecha", "numero", "operador", "registrado_en", "metodo")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(ordering="trabajador__empresa", description="Empresa")
    def empresa(self, obj):
        return obj.trabajador.empresa
