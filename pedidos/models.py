import secrets

from django.db import models

from consumos.models import Consumo
from locales.models import Local
from menus.models import Acompanamiento, PlatoDia


# Pedidos anteriores a la mesa obligatoria; los nuevos sin mesa son siempre «Despacho».
SIN_MESA = "Sin mesa"


def nuevo_token_etiqueta():
    return secrets.token_urlsafe(32)
# Colaciones que se envían a las empresas: única forma de confirmar un pedido sin mesa.
DESPACHO = "Despacho"


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
    mesa = models.ForeignKey(
        "mesas.Mesa", on_delete=models.PROTECT, null=True, blank=True, related_name="pedidos",
        help_text="Mesa activa en el escáner al confirmar. Vacío = sin mesa / para llevar.",
    )
    # Copia del nombre al confirmar: renombrar o desactivar la mesa no altera el historial.
    mesa_nombre = models.CharField(max_length=60, default=SIN_MESA)
    # Pedido de despacho: colación que se envía a la empresa (sin mesa, solo administrador).
    es_despacho = models.BooleanField(default=False)
    # Token de la etiqueta del envase. Distinto del QR del trabajador, que nunca se imprime
    # en etiquetas, guías ni hojas de reparto.
    token_etiqueta = models.CharField(max_length=43, unique=True, default=nuevo_token_etiqueta, editable=False)
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


class EtiquetaMarmita(models.Model):
    """Etiqueta de una marmita de despacho: un plato (y acompañamiento) de una empresa en un día.

    La cantidad se calcula de los pedidos vigentes; aquí solo vive su token (el QR que se
    escanea al verificar el despacho), distinto del QR de cualquier trabajador.
    """

    local = models.ForeignKey(Local, on_delete=models.PROTECT, related_name="etiquetas_marmita")
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="etiquetas_marmita")
    fecha = models.DateField()
    plato = models.ForeignKey(PlatoDia, on_delete=models.PROTECT, related_name="etiquetas_marmita")
    acompanamiento = models.ForeignKey(
        Acompanamiento, on_delete=models.PROTECT, null=True, blank=True, related_name="etiquetas_marmita"
    )
    token = models.CharField(max_length=43, unique=True, default=nuevo_token_etiqueta, editable=False)

    class Meta:
        verbose_name = "Etiqueta de marmita"
        verbose_name_plural = "Etiquetas de marmita"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "fecha", "plato", "acompanamiento"],
                nulls_distinct=False,
                name="una_etiqueta_por_marmita",
            )
        ]

    def __str__(self):
        return f"{self.plato} + {self.acompanamiento}" if self.acompanamiento_id else str(self.plato)
