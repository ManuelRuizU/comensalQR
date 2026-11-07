import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Operador",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("activo", models.BooleanField(default=True)),
                ("usuario", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="perfil_operador", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Operador",
                "verbose_name_plural": "Operadores",
                "ordering": ["usuario__last_name", "usuario__first_name"],
            },
        ),
    ]