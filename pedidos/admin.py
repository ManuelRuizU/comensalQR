from django.contrib import admin

from .models import Pedido, PedidoItem


class PedidoItemInline(admin.TabularInline):
    model = PedidoItem
    extra = 0
    can_delete = False
    fields = ("tiempo_nombre", "plato_nombre", "acompanamiento_nombre")
    readonly_fields = fields


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    """Solo consulta: los pedidos se crean, cambian y anulan mediante los servicios."""

    list_display = ("folio_texto", "fecha", "local", "mesa_nombre", "estado", "consumo")
    list_filter = ("estado", "fecha", "local")
    inlines = [PedidoItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
