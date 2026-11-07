from django.conf import settings
from django.db import models

from trabajadores.models import Trabajador


class Consumo(models.Model):
    trabajador = models.ForeignKey(
        Trabajador,
        on_delete=models.PROTECT,
        related_name="consumos",
    )
    fecha = models.DateField()
    registrado_en = models.DateTimeField(auto_now_add=True)
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="consumos_registrados",
    )

    class Meta:
        ordering = ["-registrado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["trabajador", "fecha"],
                name="consumo_unico_por_trabajador_y_fecha",
            )
        ]
        verbose_name = "Consumo"
        verbose_name_plural = "Consumos"

    def __str__(self):
        return f"{self.trabajador} - {self.fecha}"
