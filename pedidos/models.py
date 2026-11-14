from django.db import models

from consumos.models import Consumo
from locales.models import Local
from menus.models import Acompanamiento, PlatoDia


SIN_MESA = "Sin mesa"


class Pedido(models.Model):
    """Pedido de un comensal. Nace junto con su consumo al confirmar, nunca antes."""

    PENDIENTE = "pendiente"
    LISTO = "listo"
    ENTREGADO = "entregado"
    ANULADO = "anulado"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (LISTO, "Listo"),
        (ENTREGADO, "Entregado"),
        (ANULADO, "Anulado"),
    ]

    consumo = models.OneToOneField(Consumo, on_delete=models.PROTECT, related_name="pedido")
    local = models.ForeignKey(Local, on_delete=models.PROTECT, related_name="pedidos")
    fecha = models.DateField(help_text="Día del pedido en America/Santiago.")
    folio = models.PositiveIntegerField()
    # La mesa (FK a mesas.Mesa) se agrega en la Fase 2; hasta entonces todo es «Sin mesa».
    mesa_nombre = models.CharField(max_length=30, default=SIN_MESA)
    clave_idempotencia = models.UUIDField(unique=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    creado = models.DateTimeField(auto_now_add=True)
    listo_en = models.DateTimeField(null=True, blank=True)
    entregado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha", "-folio"]
        unique_together = [("local", "fecha", "folio")]
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"

    def __str__(self):
        return f"Pedido {self.folio_texto} · {self.local}"

    @property
    def folio_texto(self):
        return f"{self.folio:04d}"


class PedidoItem(models.Model):
    """Una línea del pedido: un plato (y su acompañamiento) de un tiempo.

    Guarda copia de los nombres para que editar el menú no altere el historial.
    """

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="items")
    tiempo_nombre = models.CharField(max_length=40)
    plato = models.ForeignKey(PlatoDia, on_delete=models.PROTECT, related_name="pedido_items")
    plato_nombre = models.CharField(max_length=80)
    acompanamiento = models.ForeignKey(
        Acompanamiento, on_delete=models.PROTECT, null=True, blank=True, related_name="pedido_items"
    )
    acompanamiento_nombre = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["plato__tiempo__orden", "id"]
        verbose_name = "Ítem del pedido"
        verbose_name_plural = "Ítems del pedido"

    def __str__(self):
        if self.acompanamiento_nombre:
            return f"{self.plato_nombre} + {self.acompanamiento_nombre}"
        return self.plato_nombre


class FolioDiario(models.Model):
    """Contador de folios por local y día. Se bloquea su fila al confirmar."""

    local = models.ForeignKey(Local, on_delete=models.PROTECT, related_name="folios")
    fecha = models.DateField()
    ultimo = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("local", "fecha")]
        verbose_name = "Folio diario"
        verbose_name_plural = "Folios diarios"
