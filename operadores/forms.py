from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db.models import Q
from django.utils.safestring import mark_safe

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


def normalizar_correo(correo):
    return (correo or "").strip().lower()


class _ClaveSeguraMixin:
    """Valida que la clave y su confirmación coincidan y cumplan las reglas de Django."""

    campo_clave = "clave"
    campo_confirmacion = "clave_confirmacion"

    def _usuario_para_validar(self):
        raise NotImplementedError

    def _validar_clave(self, cleaned_data):
        clave = cleaned_data.get(self.campo_clave)
        confirmacion = cleaned_data.get(self.campo_confirmacion)
        if not clave and not confirmacion:
            return
        if clave != confirmacion:
            self.add_error(self.campo_confirmacion, "Las claves no coinciden.")
            return
        try:
            password_validation.validate_password(clave, user=self._usuario_para_validar())
        except ValidationError as error:
            self.add_error(self.campo_clave, error)


class AdministradorForm(_ClaveSeguraMixin, forms.Form):
    nombre = forms.CharField(max_length=150, label="Nombre")
    apellido = forms.CharField(max_length=150, label="Apellido")
    correo = forms.EmailField(label="Correo", help_text="Con este correo inicia sesión.")
    local = forms.ModelChoiceField(
        label="Local",
        queryset=Local.objects.filter(activo=True),
        empty_label="Selecciona el local",
        help_text="Los almuerzos que escanee quedarán asociados a este local.",
    )
    clave = forms.CharField(
        label="Clave",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=mark_safe(password_validation.password_validators_help_text_html()),
    )
    clave_confirmacion = forms.CharField(
        label="Repite la clave",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, con_local=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not con_local:
            # En el registro inicial el local se crea en el mismo formulario.
            del self.fields["local"]

    def clean_correo(self):
        correo = normalizar_correo(self.cleaned_data["correo"])
        if User.objects.filter(Q(username__iexact=correo) | Q(email__iexact=correo)).exists():
            raise ValidationError("Ya existe un usuario con este correo.")
        return correo

    def _usuario_para_validar(self):
        datos = self.cleaned_data
        return User(
            username=datos.get("correo", ""),
            email=datos.get("correo", ""),
            first_name=datos.get("nombre", ""),
            last_name=datos.get("apellido", ""),
        )

    def clean(self):
        cleaned_data = super().clean()
        self._validar_clave(cleaned_data)
        return cleaned_data


class AdministradorEditarForm(_ClaveSeguraMixin, forms.Form):
    campo_clave = "nueva_clave"
    campo_confirmacion = "nueva_clave_confirmacion"

    local = forms.ModelChoiceField(
        label="Local",
        queryset=Local.objects.none(),
        empty_label="Selecciona el local",
        help_text="Los almuerzos que escanee quedarán asociados a este local.",
    )
    activo = forms.BooleanField(label="Administrador activo", required=False)
    nueva_clave = forms.CharField(
        label="Nueva clave",
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "placeholder": "Déjalo vacío para mantener la clave"}
        ),
    )
    nueva_clave_confirmacion = forms.CharField(
        label="Repite la nueva clave",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, usuario, local_actual=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        locales = Local.objects.filter(activo=True)
        if local_actual is not None:
            locales = locales | Local.objects.filter(pk=local_actual.pk)
        self.fields["local"].queryset = locales

    def _usuario_para_validar(self):
        return self.usuario

    def clean(self):
        cleaned_data = super().clean()
        self._validar_clave(cleaned_data)
        return cleaned_data
