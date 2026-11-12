from django.contrib import admin

from .models import Trabajador


@admin.register(Trabajador)
class TrabajadorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "apellido", "rut", "empresa", "almuerzos_diarios", "activo", "eliminado_en")
    list_filter = ("activo", "eliminado_en", "empresa")
    search_fields = ("nombre", "apellido", "rut")
    readonly_fields = ("token_qr",)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj:
            if obj.eliminado_en:
                readonly_fields.append("activo")
            if obj.eliminado_en or obj.consumos.exists():
                readonly_fields.append("empresa")
        return readonly_fields

    def save_model(self, request, obj, form, change):
        fue_eliminado = obj.eliminado_en or (
            change
            and self.model.objects.filter(pk=obj.pk, eliminado_en__isnull=False).exists()
        )
        if fue_eliminado:
            obj.activo = False
        if change:
            empresa_original = self.model.objects.filter(pk=obj.pk).values_list(
                "empresa_id", flat=True
            ).first()
            if (
                empresa_original is not None
                and obj.empresa_id != empresa_original
                and self.model.objects.filter(pk=obj.pk, consumos__isnull=False).exists()
            ):
                obj.empresa_id = empresa_original
        super().save_model(request, obj, form, change)
