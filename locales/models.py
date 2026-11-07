from django.db import models


class Local(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    direccion = models.CharField(max_length=250)
    telefono = models.CharField(max_length=30, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Local"
        verbose_name_plural = "Locales"

    def __str__(self):
        return self.nombre
