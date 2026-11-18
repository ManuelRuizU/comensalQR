import secrets

from django.db import migrations, models

import pedidos.models


def rellenar_tokens(apps, schema_editor):
    """Cada pedido existente recibe su propio token de etiqueta (únicos, no repetidos)."""
    Pedido = apps.get_model("pedidos", "Pedido")
    for pedido in Pedido.objects.filter(token_etiqueta__isnull=True).only("pk"):
        pedido.token_etiqueta = secrets.token_urlsafe(32)
        pedido.save(update_fields=["token_etiqueta"])


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0002_pedido_mesa"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pedido",
            name="mesa_nombre",
            field=models.CharField(default="Sin mesa", max_length=60),
        ),
        migrations.AddField(
            model_name="pedido",
            name="es_despacho",
            field=models.BooleanField(default=False),
        ),
        # Tres pasos: agregar vacío, rellenar uno distinto por pedido, y recién ahí exigir único.
        migrations.AddField(
            model_name="pedido",
            name="token_etiqueta",
            field=models.CharField(editable=False, max_length=43, null=True),
        ),
        migrations.RunPython(rellenar_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pedido",
            name="token_etiqueta",
            field=models.CharField(
                default=pedidos.models.nuevo_token_etiqueta, editable=False, max_length=43, unique=True
            ),
        ),
    ]
