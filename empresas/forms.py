from django import forms

from .models import Empresa
from .validators import normalizar_rut


class EmpresaForm(forms.ModelForm):
    """Solo administradores acceden a este formulario (vistas de empresas)."""

    def clean_rut(self):
        return normalizar_rut(self.cleaned_data["rut"])

    class Meta:
        model = Empresa
        widgets = {"hora_cierre_despacho": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}
        fields = [
            "rut",
            "nombre",
            "direccion",
            "telefono",
            "encargado_personal",
            "encargado_pagos",
            "almuerzos_diarios",
            "hora_cierre_despacho",
            "tipo_envase",
            "activa",
        ]
        labels = {
            "nombre": "Nombre de la empresa",
            "rut": "RUT de la empresa",
            "direccion": "Direccion",
            "telefono": "Telefono",
            "encargado_personal": "Encargado del personal",
            "encargado_pagos": "Encargado de los pagos",
            "almuerzos_diarios": "Almuerzos diarios por trabajador",
            "hora_cierre_despacho": "Cierre de su lista de despacho",
            "tipo_envase": "Envase del despacho",
            "activa": "Empresa activa",
        }
