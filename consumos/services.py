from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from trabajadores.models import Trabajador

from .models import Consumo


class TrabajadorNoDisponible(Exception):
    """El trabajador no puede registrar nuevos consumos."""


@dataclass
class ResultadoConsumo:
    consumo: Consumo
    creado: bool
    usados: int
    cupo: int

    def __iter__(self):
        # Compatibilidad con el uso anterior: consumo, creado = registrar_consumo_diario(...)
        return iter((self.consumo, self.creado))


def registrar_consumo_diario(trabajador_id, operador, fecha=None, metodo=Consumo.METODO_QR):
    """Único punto de escritura para consumos identificados por cualquier método.

    Registra un almuerzo si el trabajador aún tiene cupo diario en su empresa.
    Si el cupo está agotado devuelve el último consumo del día con creado=False.
    """
    fecha = fecha or timezone.localdate()

    with transaction.atomic():
        # El bloqueo de la fila del trabajador serializa los registros concurrentes
        # del mismo QR, de modo que el conteo del cupo es consistente.
        trabajador = (
            Trabajador.objects.select_for_update()
            .select_related("empresa")
            .filter(pk=trabajador_id)
            .first()
        )
        if (
            trabajador is None
            or not trabajador.activo
            or trabajador.eliminado_en is not None
            or not trabajador.empresa.activa
        ):
            raise TrabajadorNoDisponible

        cupo = trabajador.cupo_diario
        consumos_dia = Consumo.objects.filter(trabajador=trabajador, fecha=fecha)
        usados = consumos_dia.count()
        if usados >= cupo:
            return ResultadoConsumo(consumos_dia.order_by("-numero").first(), False, usados, cupo)

        # El número siguiente se toma del máximo existente (no del conteo) para que un
        # hueco en la numeración no provoque una colisión y un falso «cupo agotado».
        ultimo_numero = consumos_dia.aggregate(maximo=Max("numero"))["maximo"] or 0
        try:
            with transaction.atomic():
                consumo = Consumo.objects.create(
                    trabajador=trabajador,
                    fecha=fecha,
                    numero=ultimo_numero + 1,
                    operador=operador,
                    metodo=metodo,
                )
        except IntegrityError:
            existente = consumos_dia.order_by("-numero").first()
            if existente is None:
                raise
            return ResultadoConsumo(existente, False, consumos_dia.count(), cupo)

        return ResultadoConsumo(consumo, True, usados + 1, cupo)
