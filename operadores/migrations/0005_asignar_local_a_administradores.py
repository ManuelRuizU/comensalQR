from django.db import migrations


def asignar_local_unico(apps, schema_editor):
    """Con un único local, los administradores existentes escanean en ese local.

    Con varios locales (o ninguno) no se asigna nada: se hace desde Administradores.
    """
    Local = apps.get_model("locales", "Local")
    Administrador = apps.get_model("operadores", "Administrador")
    Consumo = apps.get_model("consumos", "Consumo")
    User = apps.get_model("auth", "User")

    locales = list(Local.objects.all()[:2])
    if len(locales) != 1:
        return
    local = locales[0]
    for usuario in User.objects.filter(is_staff=True, perfil_administrador__isnull=True):
        Administrador.objects.create(usuario=usuario, local=local)
    Consumo.objects.filter(local__isnull=True).update(local=local)


class Migration(migrations.Migration):

    dependencies = [
        ("operadores", "0004_administrador"),
        ("consumos", "0005_asignar_local_unico"),
    ]

    operations = [
        migrations.RunPython(asignar_local_unico, migrations.RunPython.noop),
    ]
