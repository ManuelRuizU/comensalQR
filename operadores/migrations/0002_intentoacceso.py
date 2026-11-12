from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operadores", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="IntentoAcceso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("clave", models.CharField(max_length=64, unique=True)),
                ("intentos", models.PositiveSmallIntegerField(default=0)),
                ("ventana_desde", models.DateTimeField()),
                ("bloqueado_hasta", models.DateTimeField(blank=True, null=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Intento de acceso",
                "verbose_name_plural": "Intentos de acceso",
                "indexes": [models.Index(fields=["actualizado_en"], name="login_attempt_updated_idx")],
            },
        ),
    ]
