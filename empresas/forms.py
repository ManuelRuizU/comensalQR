from django import forms

from .models import Empresa


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = [
            "rut",
            "nombre",
            "direccion",
            "telefono",
            "encargado_personal",
            "encargado_pagos",
            "activa",
        ]
        labels = {
            "nombre": "Nombre de la empresa",
            "rut": "RUT de la empresa",
            "direccion": "Direccion",
            "telefono": "Telefono",
            "encargado_personal": "Encargado del personal",
            "encargado_pagos": "Encargado de los pagos",
            "activa": "Empresa activa",
        }
