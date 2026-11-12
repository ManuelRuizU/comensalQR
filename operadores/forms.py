from django import forms
from django.core.validators import RegexValidator

from locales.models import Local


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


def _campo_local():
    return forms.ModelChoiceField(
        label="Local",
        queryset=Local.objects.filter(activo=True),
        empty_label="Selecciona el local",
        error_messages={"required": "Asigna el local donde trabajará el operador."},
        help_text="Los almuerzos que registre quedarán asociados a este local.",
    )


class OperadorForm(forms.Form):
    solicitud_id = forms.CharField(widget=forms.HiddenInput)
    nombre = forms.CharField(max_length=150, label="Nombre")
    apellido = forms.CharField(max_length=150, label="Apellido")
    local = _campo_local()
    clave = forms.CharField(
        label="Clave de acceso",
        min_length=LARGO_CLAVE,
        max_length=LARGO_CLAVE,
        strip=False,
        validators=[CLAVE_VALIDATOR],
        widget=_clave_widget(),
    )


class OperadorEditarForm(forms.Form):
    local = _campo_local()
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

    def __init__(self, *args, local_actual=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Se permite conservar un local que se haya desactivado después de asignarlo.
        locales = Local.objects.filter(activo=True)
        if local_actual is not None:
            locales = Local.objects.filter(activo=True) | Local.objects.filter(pk=local_actual.pk)
        self.fields["local"].queryset = locales
