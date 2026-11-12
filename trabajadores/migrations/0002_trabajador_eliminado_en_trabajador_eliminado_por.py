import django.conf
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(django.conf.settings.AUTH_USER_MODEL),
        ("trabajadores", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="trabajador",
            name="eliminado_en",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="trabajador",
            name="eliminado_por",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="trabajadores_eliminados",
                to=django.conf.settings.AUTH_USER_MODEL,
            ),
        ),
    ]
