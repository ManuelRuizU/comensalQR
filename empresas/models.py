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
    hora_cierre_despacho = models.TimeField(
        null=True, blank=True,
        help_text="Vacío = usa la hora de cierre del local.",
    )
    ENVASE_INDIVIDUAL = "individual"
    ENVASE_MARMITA = "marmita"
    TIPOS_ENVASE = [(ENVASE_INDIVIDUAL, "Individual"), (ENVASE_MARMITA, "Marmita")]
    tipo_envase = models.CharField(max_length=12, choices=TIPOS_ENVASE, default=ENVASE_INDIVIDUAL)
    usa_codigo_interno = models.BooleanField(
        default=False,
        help_text="Muestra el código interno del trabajador en su ficha, la importación, "
        "la guía de despacho y la búsqueda manual del escáner.",
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
