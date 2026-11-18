"""Verificar despacho: el encargado escanea las etiquetas antes de que salga el despacho.

Es solo control: registra quién verificó cada etiqueta y a qué hora. No crea ni modifica
consumos ni pedidos. Las etiquetas son de pedido (envase individual) o de marmita.
"""

from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction

from empresas.models import Empresa

from . import despacho
from .models import EtiquetaMarmita, Pedido, VerificacionEtiqueta

OK = "ok"
DUPLICADA = "duplicada"
RECHAZADA = "rechazada"


@dataclass
class Progreso:
    verificados: int
    total: int
    faltantes: list = field(default_factory=list)

    @property
    def listo(self):
        return self.total > 0 and self.verificados == self.total


@dataclass
class Lectura:
    estado: str          # ok | duplicada | rechazada
    mensaje: str
    progreso: Progreso


def _es_marmita(empresa):
    return empresa.tipo_envase == Empresa.ENVASE_MARMITA


def progreso(empresa, local, fecha):
    """Cuántas etiquetas faltan: pedidos vigentes (individual) o marmitas (plato + acompañamiento)."""
    pedidos = list(despacho.pedidos_de_despacho(empresa, local, fecha))
    if not _es_marmita(empresa):
        verificados = set(
            VerificacionEtiqueta.objects.filter(pedido__in=pedidos).values_list("pedido_id", flat=True)
        )
        faltantes = [str(p.consumo.trabajador) for p in pedidos if p.pk not in verificados]
        return Progreso(len(pedidos) - len(faltantes), len(pedidos), faltantes)

    combinaciones = {}
    for pedido in pedidos:
        for item in pedido.items.all():
            combinaciones.setdefault((item.plato_id, item.acompanamiento_id), str(item))
    verificadas = {
        (m.plato_id, m.acompanamiento_id)
        for m in EtiquetaMarmita.objects.filter(empresa=empresa, fecha=fecha, verificacion__isnull=False)
    }
    faltantes = [nombre for clave, nombre in sorted(combinaciones.items(), key=lambda par: par[1]) if clave not in verificadas]
    return Progreso(len(combinaciones) - len(faltantes), len(combinaciones), faltantes)


def verificar(usuario, empresa, local, fecha, token):
    """Registra la lectura de una etiqueta. Rechaza las de otra empresa, otro día o anuladas."""
    if not (usuario.is_authenticated and usuario.is_staff):
        raise PermissionDenied("Solo un administrador verifica despachos.")
    token = (token or "").strip()

    def lectura(estado, mensaje):
        return Lectura(estado, mensaje, progreso(empresa, local, fecha))

    pedido = Pedido.objects.select_related("consumo__trabajador__empresa").filter(token_etiqueta=token).first()
    marmita = None if pedido else EtiquetaMarmita.objects.select_related("empresa").filter(token=token).first()
    if pedido is None and marmita is None:
        return lectura(RECHAZADA, "No es una etiqueta de despacho.")

    if pedido is not None:
        empresa_etiqueta, fecha_etiqueta = pedido.consumo.trabajador.empresa, pedido.fecha
        nombre = str(pedido.consumo.trabajador)
    else:
        empresa_etiqueta, fecha_etiqueta, nombre = marmita.empresa, marmita.fecha, str(marmita)
    if empresa_etiqueta.pk != empresa.pk:
        return lectura(RECHAZADA, f"Etiqueta de otra empresa ({empresa_etiqueta}): sepárala de este despacho.")
    if fecha_etiqueta != fecha:
        return lectura(RECHAZADA, f"Etiqueta de otro día ({fecha_etiqueta:%d/%m/%Y}).")
    if pedido is not None and (not pedido.es_despacho or pedido.estado == Pedido.ANULADO):
        return lectura(RECHAZADA, f"{nombre}: el pedido está anulado o no es de despacho.")
    if (pedido is not None) == _es_marmita(empresa):
        return lectura(RECHAZADA, "Esta etiqueta no corresponde al tipo de envase de la empresa.")

    try:
        with transaction.atomic():
            VerificacionEtiqueta.objects.create(
                empresa=empresa, fecha=fecha, pedido=pedido, marmita=marmita, verificado_por=usuario
            )
    except IntegrityError:
        return lectura(DUPLICADA, f"{nombre}: ya estaba verificada.")
    return lectura(OK, f"{nombre}: verificada.")
