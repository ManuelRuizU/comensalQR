from django import forms

from .models import Empresa
from .validators import normalizar_rut


class EmpresaForm(forms.ModelForm):
    def clean_rut(self):
        return normalizar_rut(self.cleaned_data["rut"])

    class Meta:
        model = Empresa
        fields = [
            "rut",
            "nombre",
            "direccion",
            "telefono",
            "encargado_personal",
            "encargado_pagos",
            "almuerzos_diarios",
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
            "activa": "Empresa activa",
        }
