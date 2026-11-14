from django.conf import settings
from django.db import models

from trabajadores.models import Trabajador


class Consumo(models.Model):
    METODO_QR = "qr"
    METODO_RUT = "rut"
    METODOS = [(METODO_QR, "QR"), (METODO_RUT, "Manual por RUT")]

    trabajador = models.ForeignKey(
        Trabajador,
        on_delete=models.PROTECT,
        related_name="consumos",
    )
    fecha = models.DateField()
    numero = models.PositiveSmallIntegerField(
        default=1,
        help_text="Número de almuerzo del trabajador en el día (1, 2, ...).",
    )
    registrado_en = models.DateTimeField(auto_now_add=True)
    metodo = models.CharField(
        max_length=10,
        choices=METODOS,
        default=METODO_QR,
        help_text="Cómo se identificó al trabajador al registrar el consumo.",
    )
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="consumos_registrados",
    )
    local = models.ForeignKey(
        "locales.Local",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="consumos",
        help_text="Local donde se registró el consumo (el del operador al momento del registro).",
    )

    # Anulación: solo mediante consumos.services.anular_consumo (administrador, con motivo).
    # Un consumo anulado no cuenta para el cupo ni para los totales, y no se cobra.
    anulado = models.BooleanField(default=False)
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="consumos_anulados",
    )
    anulado_en = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-registrado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["trabajador", "fecha", "numero"],
                name="consumo_unico_por_trabajador_fecha_numero",
            )
        ]
        verbose_name = "Consumo"
        verbose_name_plural = "Consumos"

    def __str__(self):
        return f"{self.trabajador} - {self.fecha}"


def consumos_vigentes():
    """Consumos que cuentan para cupos y totales (excluye los anulados)."""
    return Consumo.objects.filter(anulado=False)
