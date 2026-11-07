from django.contrib import admin

from .models import Consumo


@admin.register(Consumo)
class ConsumoAdmin(admin.ModelAdmin):
    list_display = ("trabajador", "empresa", "fecha", "registrado_en", "operador")
    list_filter = ("fecha", "trabajador__empresa")
    search_fields = ("trabajador__nombre", "trabajador__apellido", "trabajador__rut")
    readonly_fields = ("registrado_en",)

    @admin.display(ordering="trabajador__empresa", description="Empresa")
    def empresa(self, obj):
        return obj.trabajador.empresa
