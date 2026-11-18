import secrets

from django.db import models

from locales.models import Local


def nuevo_token_mesa():
    # 32 bytes aleatorios → 43 caracteres URL-safe. Nunca tiene forma de UUID,
    # así el escáner distingue un QR de mesa de uno de trabajador por su formato.
    return secrets.token_urlsafe(32)


class Mesa(models.Model):
    local = models.ForeignKey(Local, on_delete=models.PROTECT, related_name="mesas")
    nombre = models.CharField(max_length=30)
    # El QR contiene solo este token: ningún dato del local ni de la mesa.
    token = models.CharField(max_length=43, unique=True, default=nuevo_token_mesa, editable=False)
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["local", "nombre"]
        unique_together = [("local", "nombre")]
        verbose_name = "Mesa"
        verbose_name_plural = "Mesas"

    def __str__(self):
        return self.nombre
