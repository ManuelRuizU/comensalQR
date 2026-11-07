from django.db import models


class Empresa(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    rut = models.CharField(max_length=12, unique=True)
    direccion = models.CharField(max_length=250)
    telefono = models.CharField(max_length=30, blank=True)
    encargado_personal = models.CharField(max_length=150)
    encargado_pagos = models.CharField(max_length=150, blank=True)
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"

    def __str__(self):
        return self.nombre
