from django import forms
from django.db.models import Q

from empresas.models import Empresa
from empresas.validators import normalizar_rut

from .models import Trabajador


class TrabajadorForm(forms.ModelForm):
    def clean_rut(self):
        return normalizar_rut(self.cleaned_data["rut"])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        empresas_activas = Empresa.objects.filter(activa=True)
        if self.instance.pk:
            empresas_activas = Empresa.objects.filter(
                Q(activa=True) | Q(pk=self.instance.empresa_id)
            )
        self.fields["empresa"].queryset = empresas_activas
        if self.instance.pk and self.instance.consumos.exists():
            # Sus consumos ya se cobran a esta empresa: cambiarla alteraría el historial.
            self.fields["empresa"].disabled = True
            self.fields["empresa"].help_text = "No se puede cambiar: el trabajador ya tiene consumos registrados."

    class Meta:
        model = Trabajador
        fields = ["empresa", "nombre", "apellido", "rut", "almuerzos_diarios", "activo"]
        labels = {
            "nombre": "Nombre",
            "apellido": "Apellido",
            "rut": "RUT",
            "empresa": "Empresa",
            "almuerzos_diarios": "Almuerzos diarios (excepción)",
            "activo": "Trabajador activo",
        }

    def clean(self):
        cleaned_data = super().clean()
        if (
            self.instance.pk
            and self.instance.eliminado_en
            and cleaned_data.get("activo")
        ):
            self.add_error("activo", "Un trabajador eliminado no puede reactivarse.")
        return cleaned_data
