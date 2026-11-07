from django.db import migrations, models


def completar_datos_existentes(apps, schema_editor):
    empresa_model = apps.get_model("empresas", "Empresa")

    for empresa in empresa_model.objects.all():
        cambios = {}
        if not empresa.rut:
            cambios["rut"] = f"PEND-{empresa.pk:06d}"
        if not empresa.direccion:
            cambios["direccion"] = "Por completar"
        if not empresa.encargado_personal:
            cambios["encargado_personal"] = "Por completar"
        if cambios:
            empresa_model.objects.filter(pk=empresa.pk).update(**cambios)


class Migration(migrations.Migration):
    dependencies = [
        ("empresas", "0002_empresa_direccion_empresa_encargado_pagos_and_more"),
    ]

    operations = [
        migrations.RunPython(completar_datos_existentes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="empresa",
            name="rut",
            field=models.CharField(max_length=12, unique=True),
        ),
        migrations.AlterField(
            model_name="empresa",
            name="direccion",
            field=models.CharField(max_length=250),
        ),
        migrations.AlterField(
            model_name="empresa",
            name="encargado_personal",
            field=models.CharField(max_length=150),
        ),
    ]