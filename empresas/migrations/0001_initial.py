from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Empresa",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=150, unique=True)),
                ("activa", models.BooleanField(default=True)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Empresa",
                "verbose_name_plural": "Empresas",
                "ordering": ["nombre"],
            },
        ),
    ]
