from django import forms
from django.core.validators import RegexValidator


CLAVE_VALIDATOR = RegexValidator(
    regex=r"^[0-9]{6}$",
    message="La clave debe contener exactamente 6 digitos numericos.",
)


def _clave_widget(placeholder="6 digitos"):
    return forms.PasswordInput(
        attrs={
            "inputmode": "numeric",
            "autocomplete": "new-password",
            "pattern": "[0-9]{6}",
            "placeholder": placeholder,
        }
    )


class OperadorForm(forms.Form):
    solicitud_id = forms.CharField(widget=forms.HiddenInput)
    nombre = forms.CharField(max_length=150, label="Nombre")
    apellido = forms.CharField(max_length=150, label="Apellido")
    clave = forms.CharField(
        label="Clave de acceso",
        min_length=6,
        max_length=6,
        strip=False,
        validators=[CLAVE_VALIDATOR],
        widget=_clave_widget(),
    )


class OperadorEditarForm(forms.Form):
    activo = forms.BooleanField(label="Operador activo", required=False)
    nueva_clave = forms.CharField(
        label="Nueva clave de acceso",
        required=False,
        min_length=6,
        max_length=6,
        strip=False,
        validators=[CLAVE_VALIDATOR],
        widget=_clave_widget("Déjalo vacío para mantener la clave"),
    )
