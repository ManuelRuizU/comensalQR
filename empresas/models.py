from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .validators import normalizar_rut, validar_rut


class Empresa(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    rut = models.CharField(max_length=12, unique=True, validators=[validar_rut])
    direccion = models.CharField(max_length=250)
    telefono = models.CharField(max_length=30, blank=True)
    encargado_personal = models.CharField(max_length=150)
    encargado_pagos = models.CharField(max_length=150, blank=True)
    almuerzos_diarios = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Almuerzos diarios autorizados por trabajador, salvo excepción individual.",
    )
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()
        self.rut = normalizar_rut(self.rut)

    def save(self, *args, **kwargs):
        self.rut = normalizar_rut(self.rut)
        super().save(*args, **kwargs)
