from django import forms
from django.db.models import Q

from empresas.models import Empresa
from empresas.validators import normalizar_rut

from .models import Trabajador, normalizar_codigo


class TrabajadorForm(forms.ModelForm):
    def clean_rut(self):
        return normalizar_rut(self.cleaned_data["rut"])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        empresas_activas = Empresa.objects.filter(activa=True)
        if self.instance.pk:
            empresas_activas = Empresa.objects.filter(
                Q(activa=True) | Q(pk=self.instance.empresa_id)
            )
        self.fields["empresa"].queryset = empresas_activas
        if self.instance.pk and self.instance.consumos.exists():
            # Sus consumos ya se cobran a esta empresa: cambiarla alteraría el historial.
            self.fields["empresa"].disabled = True
            self.fields["empresa"].help_text = "No se puede cambiar: el trabajador ya tiene consumos registrados."
        self._ajustar_codigo_interno()

    def _ajustar_codigo_interno(self):
        """El código interno solo existe para empresas con usa_codigo_interno.

        Si la empresa está fija (no se puede cambiar) el servidor decide; si se elige en
        el formulario, el campo se muestra con JS solo al elegir una empresa que lo usa
        (data-codigo-interno en el selector) y clean() descarta lo que no corresponda.
        """
        campo_empresa = self.fields["empresa"]
        if campo_empresa.disabled:
            usan = [self.instance.empresa_id] if self.instance.empresa.usa_codigo_interno else []
        else:
            usan = list(campo_empresa.queryset.filter(usa_codigo_interno=True).values_list("pk", flat=True))
        if not usan:
            del self.fields["codigo_interno"]
            return
        campo_empresa.widget.attrs["data-codigo-interno"] = ",".join(str(pk) for pk in usan)
        self.fields["codigo_interno"].help_text = "Opcional. Único dentro de la empresa; sirve para buscarlo en el registro manual."

    def clean_codigo_interno(self):
        return normalizar_codigo(self.cleaned_data.get("codigo_interno"))

    class Meta:
        model = Trabajador
        fields = ["empresa", "nombre", "apellido", "rut", "codigo_interno", "almuerzos_diarios", "activo"]
        labels = {
            "nombre": "Nombre",
            "apellido": "Apellido",
            "rut": "RUT",
            "codigo_interno": "Código interno",
            "empresa": "Empresa",
            "almuerzos_diarios": "Almuerzos diarios (excepción)",
            "activo": "Trabajador activo",
        }

    def clean(self):
        cleaned_data = super().clean()
        if (
            self.instance.pk
            and self.instance.eliminado_en
            and cleaned_data.get("activo")
        ):
            self.add_error("activo", "Un trabajador eliminado no puede reactivarse.")
        empresa = cleaned_data.get("empresa")
        if "codigo_interno" in self.fields and empresa is not None and not empresa.usa_codigo_interno:
            # La empresa no usa el beneficio: no se guarda lo escrito (se conserva el que tenía).
            cleaned_data["codigo_interno"] = self.instance.codigo_interno if self.instance.pk else None
        return cleaned_data
