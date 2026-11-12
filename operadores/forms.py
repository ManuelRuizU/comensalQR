from django import forms
from django.core.validators import RegexValidator


LARGO_CLAVE = 8

CLAVE_VALIDATOR = RegexValidator(
    regex=rf"^[0-9]{{{LARGO_CLAVE}}}$",
    message=f"La clave debe contener exactamente {LARGO_CLAVE} dígitos numéricos.",
)


def _clave_widget(placeholder=f"{LARGO_CLAVE} dígitos"):
    return forms.PasswordInput(
        attrs={
            "inputmode": "numeric",
            "autocomplete": "new-password",
            "pattern": f"[0-9]{{{LARGO_CLAVE}}}",
            "placeholder": placeholder,
        }
    )


class OperadorForm(forms.Form):
    solicitud_id = forms.CharField(widget=forms.HiddenInput)
    nombre = forms.CharField(max_length=150, label="Nombre")
    apellido = forms.CharField(max_length=150, label="Apellido")
    clave = forms.CharField(
        label="Clave de acceso",
        min_length=LARGO_CLAVE,
        max_length=LARGO_CLAVE,
        strip=False,
        validators=[CLAVE_VALIDATOR],
        widget=_clave_widget(),
    )


class OperadorEditarForm(forms.Form):
    activo = forms.BooleanField(label="Operador activo", required=False)
    nueva_clave = forms.CharField(
        label="Nueva clave de acceso",
        required=False,
        min_length=LARGO_CLAVE,
        max_length=LARGO_CLAVE,
        strip=False,
        validators=[CLAVE_VALIDATOR],
        widget=_clave_widget("Déjalo vacío para mantener la clave"),
    )
