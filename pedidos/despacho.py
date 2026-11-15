"""Despacho: colaciones que se envían a las empresas. Solo el administrador las registra.

El trabajador no está presente, así que no pasa por el escáner: el administrador recibe la
lista nominal de la empresa y la registra antes de la hora de cierre. Cada pedido se crea con
el mismo registrar_pedido() del local (cupo, porciones y folio con bloqueo de filas); si uno
falla, los demás se crean igual y se informa cuál falló y por qué.
"""

import datetime
from collections import Counter
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from consumos.services import AnulacionInvalida, PedidoRechazado, anular_consumo, registrar_pedido
from operadores.models import local_de_usuario

from .models import Pedido

MOTIVO_QUITADO = "Quitado de la lista de despacho antes del cierre"


class ErrorDespacho(Exception):
    def __init__(self, codigo, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _exigir_admin(usuario):
    if not (usuario.is_authenticated and usuario.is_staff):
        raise PermissionDenied("Solo un administrador gestiona los despachos.")


def hora_cierre(empresa, local):
    """La hora de cierre de la empresa, o la del local si la empresa no tiene una propia."""
    return empresa.hora_cierre_despacho or local.hora_cierre_despacho


def momento_cierre(empresa, local, fecha):
    """Fecha y hora (America/Santiago) en que la lista de despacho de ese día queda fija."""
    return timezone.make_aware(datetime.datetime.combine(fecha, hora_cierre(empresa, local)))


def lista_abierta(empresa, local, fecha, ahora=None):
    return (ahora or timezone.now()) < momento_cierre(empresa, local, fecha)


def exigir_lista_abierta(empresa, local, fecha):
    if not lista_abierta(empresa, local, fecha):
        cierre = hora_cierre(empresa, local)
        raise ErrorDespacho(
            "lista_cerrada",
            f"La lista de despacho de {empresa} cerró a las {cierre:%H:%M}: solo se puede anular con motivo.",
        )


def pedidos_de_despacho(empresa, local, fecha, incluir_anulados=False):
    pedidos = Pedido.objects.filter(
        es_despacho=True, local=local, fecha=fecha, consumo__trabajador__empresa=empresa
    ).select_related("consumo__trabajador").prefetch_related("items")
    if not incluir_anulados:
        pedidos = pedidos.exclude(estado=Pedido.ANULADO)
    return pedidos.order_by("consumo__trabajador__apellido", "consumo__trabajador__nombre")


def totales_por_plato(pedidos):
    """[(«Plato + acompañamiento», cantidad)] ordenado por cantidad, para guía, cocina y marmitas."""
    conteo = Counter(str(item) for pedido in pedidos for item in pedido.items.all())
    return sorted(conteo.items(), key=lambda par: (-par[1], par[0]))


@dataclass
class ResultadoLista:
    creados: list = field(default_factory=list)       # pedidos nuevos
    sin_cambios: list = field(default_factory=list)   # ya estaban registrados (reintento)
    quitados: list = field(default_factory=list)      # anulados por desmarcar antes del cierre
    errores: list = field(default_factory=list)       # (trabajador, código, mensaje)

    @property
    def total_errores(self):
        return len(self.errores)


def confirmar_lista(usuario, empresa, fecha, filas, quitar=()):
    """Registra la lista de despacho de una empresa para `fecha`.

    `filas`: [{"trabajador": Trabajador, "token": uuid, "seleccion": [...]}] de los marcados
    sin pedido; `quitar`: pedidos a anular porque se desmarcaron. Cada pedido va en su propia
    transacción (registrar_pedido): un rechazo no impide crear los demás.
    """
    _exigir_admin(usuario)
    local = local_de_usuario(usuario)
    if local is None:
        raise ErrorDespacho("sin_local", "Tu usuario no tiene local asignado.")
    exigir_lista_abierta(empresa, local, fecha)

    resultado = ResultadoLista()
    for fila in filas:
        trabajador = fila["trabajador"]
        if trabajador.empresa_id != empresa.pk:
            resultado.errores.append((trabajador, "otra_empresa", f"{trabajador} no es de {empresa}."))
            continue
        try:
            registro = registrar_pedido(
                trabajador.pk, usuario, fila["token"], fila["seleccion"], fecha=fecha, despacho=True
            )
        except PedidoRechazado as rechazo:
            resultado.errores.append((trabajador, rechazo.codigo, rechazo.mensaje))
            continue
        (resultado.creados if registro.creado else resultado.sin_cambios).append(registro.pedido)

    for pedido in quitar:
        try:
            anular_consumo(pedido.consumo_id, usuario, MOTIVO_QUITADO)
        except AnulacionInvalida as error:
            resultado.errores.append((pedido.consumo.trabajador, "anulacion", str(error)))
            continue
        resultado.quitados.append(pedido)
    return resultado
