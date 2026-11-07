import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("trabajadores", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Consumo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateField()),
                ("registrado_en", models.DateTimeField(auto_now_add=True)),
                ("operador", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="consumos_registrados", to=settings.AUTH_USER_MODEL)),
                ("trabajador", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="consumos", to="trabajadores.trabajador")),
            ],
            options={
                "verbose_name": "Consumo",
                "verbose_name_plural": "Consumos",
                "ordering": ["-registrado_en"],
            },
        ),
        migrations.AddConstraint(
            model_name="consumo",
            constraint=models.UniqueConstraint(fields=("trabajador", "fecha"), name="consumo_unico_por_trabajador_y_fecha"),
        ),
    ]
