import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("empresas", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Trabajador",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100)),
                ("apellido", models.CharField(max_length=100)),
                ("rut", models.CharField(max_length=12, unique=True)),
                ("activo", models.BooleanField(default=True)),
                ("token_qr", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="trabajadores", to="empresas.empresa")),
            ],
            options={
                "verbose_name": "Trabajador",
                "verbose_name_plural": "Trabajadores",
                "ordering": ["apellido", "nombre"],
            },
        ),
    ]
