from django.conf import settings
from django.db import models


class Operador(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_operador",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["usuario__last_name", "usuario__first_name"]
        verbose_name = "Operador"
        verbose_name_plural = "Operadores"

    def __str__(self):
        return self.usuario.get_full_name() or self.usuario.get_username()


class IntentoAcceso(models.Model):
    clave = models.CharField(max_length=64, unique=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    ventana_desde = models.DateTimeField()
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Intento de acceso"
        verbose_name_plural = "Intentos de acceso"
        indexes = [models.Index(fields=["actualizado_en"], name="login_attempt_updated_idx")]
