from django.db import migrations


def asignar_local_unico(apps, schema_editor):
    """Si el restaurante tiene un solo local, todo lo registrado hasta ahora ocurrió ahí.

    Con varios locales (o ninguno) no hay forma de saberlo, así que no se asigna nada.
    """
    Local = apps.get_model("locales", "Local")
    Operador = apps.get_model("operadores", "Operador")
    Consumo = apps.get_model("consumos", "Consumo")

    locales = list(Local.objects.all()[:2])
    if len(locales) != 1:
        return
    local = locales[0]
    Operador.objects.filter(local__isnull=True).update(local=local)
    Consumo.objects.filter(local__isnull=True).update(local=local)


class Migration(migrations.Migration):

    dependencies = [
        ("consumos", "0004_consumo_local"),
        ("operadores", "0003_operador_local"),
    ]

    operations = [
        migrations.RunPython(asignar_local_unico, migrations.RunPython.noop),
    ]
