from django import forms

from .models import Local


class LocalForm(forms.ModelForm):
    class Meta:
        model = Local
        fields = ["nombre", "direccion", "telefono", "activo"]
        labels = {
            "nombre": "Nombre del local",
            "direccion": "Dirección",
            "telefono": "Teléfono",
            "activo": "Local activo",
        }
