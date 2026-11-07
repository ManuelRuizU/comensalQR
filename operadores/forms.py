from django import forms
from django.core.validators import RegexValidator


class OperadorForm(forms.Form):
    nombre = forms.CharField(max_length=150, label="Nombre")
    apellido = forms.CharField(max_length=150, label="Apellido")
    clave = forms.CharField(
        label="Clave de acceso",
        min_length=4,
        max_length=6,
        strip=False,
        validators=[
            RegexValidator(
                regex=r"^\d{4,6}$",
                message="La clave debe contener solamente entre 4 y 6 digitos numericos.",
            )
        ],
        widget=forms.PasswordInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "new-password",
                "pattern": "[0-9]{4,6}",
                "placeholder": "4 a 6 digitos",
            }
        ),
    )
