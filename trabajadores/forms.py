from django import forms

from .models import Trabajador


class TrabajadorForm(forms.ModelForm):
    class Meta:
        model = Trabajador
        fields = ["empresa", "nombre", "apellido", "rut", "activo"]
        labels = {
            "nombre": "Nombre",
            "apellido": "Apellido",
            "rut": "RUT",
            "empresa": "Empresa",
            "activo": "Trabajador activo",
        }
