import uuid

from django.db import models

from empresas.models import Empresa


class Trabajador(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    rut = models.CharField(max_length=12, unique=True)
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="trabajadores",
    )
    activo = models.BooleanField(default=True)
    token_qr = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["apellido", "nombre"]
        verbose_name = "Trabajador"
        verbose_name_plural = "Trabajadores"

    def __str__(self):
        return f"{self.nombre} {self.apellido}"
