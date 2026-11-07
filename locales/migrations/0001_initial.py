from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Local",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=150, unique=True)),
                ("direccion", models.CharField(max_length=250)),
                ("telefono", models.CharField(blank=True, max_length=30)),
                ("activo", models.BooleanField(default=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Local",
                "verbose_name_plural": "Locales",
                "ordering": ["nombre"],
            },
        ),
    ]
