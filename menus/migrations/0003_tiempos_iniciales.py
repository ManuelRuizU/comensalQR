from django.db import migrations


TIEMPOS = [
    # (nombre, orden, obligatorio): solo el Fondo es obligatorio al pedir.
    ("Fondo", 1, True),
    ("Ensalada", 2, False),
    ("Postre", 3, False),
    ("Bebida", 4, False),
]


def crear_tiempos(apps, schema_editor):
    TiempoMenu = apps.get_model("menus", "TiempoMenu")
    for nombre, orden, obligatorio in TIEMPOS:
        TiempoMenu.objects.get_or_create(
            nombre=nombre, defaults={"orden": orden, "obligatorio": obligatorio}
        )


class Migration(migrations.Migration):

    dependencies = [
        ("menus", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(crear_tiempos, migrations.RunPython.noop),
    ]
