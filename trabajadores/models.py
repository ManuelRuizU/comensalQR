import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from empresas.models import Empresa
from empresas.validators import normalizar_rut, validar_rut


class Trabajador(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    rut = models.CharField(max_length=12, validators=[validar_rut])
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="trabajadores",
    )
    almuerzos_diarios = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Déjalo vacío para usar el cupo diario de la empresa.",
    )
    # Beneficio opcional por empresa (Empresa.usa_codigo_interno). No reemplaza al RUT
    # ni va en el QR. Vacío se guarda como NULL para que la unicidad no choque.
    codigo_interno = models.CharField(max_length=20, null=True, blank=True)
    activo = models.BooleanField(default=True)
    eliminado_en = models.DateTimeField(null=True, blank=True, editable=False)
    eliminado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="trabajadores_eliminados",
    )
    token_qr = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["apellido", "nombre"]
        verbose_name = "Trabajador"
        verbose_name_plural = "Trabajadores"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "rut"],
                condition=models.Q(eliminado_en__isnull=True),
                name="trabajador_rut_vigente_por_empresa_unique",
            ),
            models.UniqueConstraint(
                fields=["empresa", "codigo_interno"],
                condition=models.Q(eliminado_en__isnull=True, codigo_interno__isnull=False),
                name="trabajador_codigo_interno_vigente_por_empresa_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(eliminado_en__isnull=True) | models.Q(activo=False),
                name="trabajador_eliminado_no_activo",
            )
        ]

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

    @property
    def cupo_diario(self):
        if self.almuerzos_diarios:
            return self.almuerzos_diarios
        return self.empresa.almuerzos_diarios

    def clean(self):
        super().clean()
        self.rut = normalizar_rut(self.rut)
        # La restricción depende de eliminado_en (no editable), por lo que Django
        # no la valida en formularios; se comprueba aquí para evitar un error 500.
        if (
            self.empresa_id
            and self.eliminado_en is None
            and Trabajador.objects.filter(
                empresa_id=self.empresa_id,
                rut=self.rut,
                eliminado_en__isnull=True,
            ).exclude(pk=self.pk).exists()
        ):
            raise ValidationError(
                {"rut": "Ya existe un trabajador vigente con este RUT en la empresa."}
            )
        self.codigo_interno = normalizar_codigo(self.codigo_interno)
        if (
            self.codigo_interno
            and self.empresa_id
            and self.eliminado_en is None
            and Trabajador.objects.filter(
                empresa_id=self.empresa_id,
                codigo_interno=self.codigo_interno,
                eliminado_en__isnull=True,
            ).exclude(pk=self.pk).exists()
        ):
            raise ValidationError(
                {"codigo_interno": "Ya existe un trabajador vigente con este código interno en la empresa."}
            )

    def save(self, *args, **kwargs):
        self.rut = normalizar_rut(self.rut)
        self.codigo_interno = normalizar_codigo(self.codigo_interno)
        super().save(*args, **kwargs)


def normalizar_codigo(valor):
    """Código interno sin espacios a los lados; vacío = None (no participa de la unicidad)."""
    valor = (valor or "").strip()
    return valor or None


class TokenQRReservado(models.Model):
    token = models.UUIDField(unique=True, editable=False)
    trabajador = models.ForeignKey(
        Trabajador,
        on_delete=models.PROTECT,
        related_name="tokens_qr_reservados",
    )
    reservado_en = models.DateTimeField(auto_now_add=True)
    invalidado_en = models.DateTimeField()
    invalidado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tokens_qr_invalidados",
    )
