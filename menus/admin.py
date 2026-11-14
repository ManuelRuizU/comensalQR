from django.contrib import admin

from .models import MenuDia, MovimientoPorcion, TiempoMenu


@admin.register(TiempoMenu)
class TiempoMenuAdmin(admin.ModelAdmin):
    list_display = ("nombre", "orden", "obligatorio", "activo")


@admin.register(MenuDia)
class MenuDiaAdmin(admin.ModelAdmin):
    list_display = ("local", "fecha", "publicado")
    list_filter = ("publicado", "local")
    date_hierarchy = "fecha"

    def has_change_permission(self, request, obj=None):
        # El menú se gestiona desde la pantalla Menú del día (porciones con motivo).
        return False


@admin.register(MovimientoPorcion)
class MovimientoPorcionAdmin(admin.ModelAdmin):
    list_display = ("creado", "tipo", "plato", "acompanamiento", "cantidad", "usuario", "motivo")
    list_filter = ("tipo",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
