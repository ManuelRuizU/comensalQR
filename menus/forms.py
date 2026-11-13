from django import forms

from .models import TiempoMenu


class ItemForm(forms.Form):
    nombre = forms.CharField(max_length=80, label="Nombre")
    porciones = forms.IntegerField(
        min_value=0, required=False, label="Porciones", help_text="Vacío = sin límite."
    )
    umbral_aviso = forms.IntegerField(
        min_value=0, max_value=1000, required=False, label="Avisar desde"
    )


class PlatoForm(ItemForm):
    tiempo = forms.ModelChoiceField(queryset=TiempoMenu.objects.filter(activo=True), label="Tiempo")


class AcompanamientoForm(ItemForm):
    nombre = forms.CharField(max_length=60, label="Acompañamiento")


class AjusteForm(forms.Form):
    porciones = forms.IntegerField(min_value=0, label="Porciones cargadas")
    motivo = forms.CharField(max_length=200, label="Motivo")


class TiempoForm(forms.ModelForm):
    class Meta:
        model = TiempoMenu
        fields = ["nombre", "orden", "obligatorio", "activo"]
        labels = {"orden": "Orden", "obligatorio": "Obligatorio", "activo": "Activo"}
