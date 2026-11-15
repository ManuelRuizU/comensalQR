from django import forms

from .models import Local


class LocalForm(forms.ModelForm):
    class Meta:
        widgets = {"hora_cierre_despacho": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}
        help_texts = {"hora_cierre_despacho": "Después de esta hora la lista de despacho del día queda fija."}
        model = Local
        fields = ["nombre", "direccion", "telefono", "hora_cierre_despacho", "activo"]
        labels = {
            "nombre": "Nombre del local",
            "direccion": "Dirección",
            "telefono": "Teléfono",
            "hora_cierre_despacho": "Cierre de la lista de despacho",
            "activo": "Local activo",
        }
