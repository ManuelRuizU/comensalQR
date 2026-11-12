from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trabajadores", "0002_trabajador_eliminado_en_trabajador_eliminado_por"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="trabajador",
            constraint=models.CheckConstraint(
                condition=models.Q(eliminado_en__isnull=True) | models.Q(activo=False),
                name="trabajador_eliminado_no_activo",
            ),
        ),
    ]
