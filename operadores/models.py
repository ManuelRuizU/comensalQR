from django.conf import settings
from django.db import models


class Operador(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_operador",
    )
    local = models.ForeignKey(
        "locales.Local",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operadores",
        help_text="Local donde el operador registra los almuerzos.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["usuario__last_name", "usuario__first_name"]
        verbose_name = "Operador"
        verbose_name_plural = "Operadores"

    def __str__(self):
        return self.usuario.get_full_name() or self.usuario.get_username()


class Administrador(models.Model):
    """Datos propios del administrador. El acceso y el estado viven en el usuario
    (is_staff, is_active); aquí se guarda el local donde escanea."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_administrador",
    )
    local = models.ForeignKey(
        "locales.Local",
        on_delete=models.PROTECT,
        related_name="administradores",
        help_text="Local donde quedan los almuerzos que este administrador registra al escanear.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Administrador"
        verbose_name_plural = "Administradores"

    def __str__(self):
        return self.usuario.get_full_name() or self.usuario.get_username()


def local_de_usuario(usuario):
    """Local en el que registra consumos el usuario (administrador u operador)."""
    for relacion in ("perfil_administrador", "perfil_operador"):
        perfil = getattr(usuario, relacion, None)
        if perfil is not None and perfil.local_id:
            return perfil.local
    return None


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
