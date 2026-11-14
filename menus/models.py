from django.conf import settings
from django.db import models

from locales.models import Local


class TiempoMenu(models.Model):
    """Etapa del almuerzo (Fondo, Ensalada, Postre, Bebida). Común a todos los locales."""

    nombre = models.CharField(max_length=40, unique=True)
    orden = models.PositiveSmallIntegerField()
    obligatorio = models.BooleanField(default=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "Tiempo del menú"
        verbose_name_plural = "Tiempos del menú"

    def __str__(self):
        return self.nombre


class MenuDia(models.Model):
    local = models.ForeignKey(Local, on_delete=models.PROTECT, related_name="menus")
    fecha = models.DateField()
    # El garzón solo ve menús publicados; sin menú publicado el escáner funciona como v0.1.
    publicado = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fecha"]
        unique_together = [("local", "fecha")]
        verbose_name = "Menú del día"
        verbose_name_plural = "Menús del día"

    def __str__(self):
        return f"{self.local} · {self.fecha:%d-%m-%Y}"


class ItemStock(models.Model):
    """Base de las porciones de platos y acompañamientos."""

    porciones = models.PositiveIntegerField(
        null=True, blank=True, help_text="Vacío = sin límite (jugo, pan)."
    )
    vendidas = models.PositiveIntegerField(default=0, editable=False)
    umbral_aviso = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Avisar «quedan pocas» desde esta cantidad."
    )
    agotado = models.BooleanField(default=False, help_text="Marcado a mano.")
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True

    @property
    def sin_limite(self):
        return self.porciones is None


class PlatoDia(ItemStock):
    menu = models.ForeignKey(MenuDia, on_delete=models.CASCADE, related_name="platos")
    tiempo = models.ForeignKey(TiempoMenu, on_delete=models.PROTECT, related_name="platos")
    nombre = models.CharField(max_length=80)

    class Meta:
        ordering = ["tiempo__orden", "orden", "id"]
        verbose_name = "Plato del día"
        verbose_name_plural = "Platos del día"

    def __str__(self):
        return self.nombre


class Acompanamiento(ItemStock):
    plato = models.ForeignKey(PlatoDia, on_delete=models.CASCADE, related_name="acompanamientos")
    nombre = models.CharField(max_length=60)

    class Meta:
        ordering = ["orden", "id"]
        verbose_name = "Acompañamiento"
        verbose_name_plural = "Acompañamientos"

    def __str__(self):
        return self.nombre


class ReservaPorcion(models.Model):
    """Porción apartada por 90 s mientras el garzón arma el pedido de un comensal."""

    plato = models.ForeignKey(PlatoDia, on_delete=models.CASCADE, related_name="reservas")
    acompanamiento = models.ForeignKey(
        Acompanamiento, on_delete=models.CASCADE, null=True, blank=True, related_name="reservas"
    )
    operador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_seleccion = models.UUIDField(db_index=True)
    expira_en = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "Reserva de porción"
        verbose_name_plural = "Reservas de porciones"


class MovimientoPorcion(models.Model):
    """Registro inmutable de cada cambio en las porciones de un ítem."""

    TIPO_CARGA = "carga"
    TIPO_PEDIDO = "pedido"
    TIPO_CAMBIO = "cambio"
    TIPO_ANULACION = "anulacion"
    TIPO_AJUSTE = "ajuste"
    TIPOS = [
        (TIPO_CARGA, "Carga"),
        (TIPO_PEDIDO, "Pedido"),
        (TIPO_CAMBIO, "Cambio de plato"),
        (TIPO_ANULACION, "Anulación"),
        (TIPO_AJUSTE, "Ajuste"),
    ]

    plato = models.ForeignKey(
        PlatoDia, on_delete=models.PROTECT, null=True, blank=True, related_name="movimientos"
    )
    acompanamiento = models.ForeignKey(
        Acompanamiento, on_delete=models.PROTECT, null=True, blank=True, related_name="movimientos"
    )
    tipo = models.CharField(max_length=12, choices=TIPOS)
    cantidad = models.IntegerField(help_text="+carga/ajuste/anulación, −pedido.")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    pedido = models.ForeignKey(
        "pedidos.Pedido", on_delete=models.PROTECT, null=True, blank=True, related_name="movimientos"
    )
    motivo = models.CharField(max_length=200, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado", "id"]
        verbose_name = "Movimiento de porciones"
        verbose_name_plural = "Movimientos de porciones"
        constraints = [
            # Cada movimiento es de un solo ítem: un plato o un acompañamiento.
            models.CheckConstraint(
                condition=(
                    models.Q(plato__isnull=False, acompanamiento__isnull=True)
                    | models.Q(plato__isnull=True, acompanamiento__isnull=False)
                ),
                name="movimiento_de_un_solo_item",
            )
        ]
