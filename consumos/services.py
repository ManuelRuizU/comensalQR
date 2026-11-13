from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from operadores.models import local_de_usuario
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
        # Los anulados no cuentan para el cupo, pero su número no se reutiliza.
        todos_dia = Consumo.objects.filter(trabajador=trabajador, fecha=fecha)
        consumos_dia = todos_dia.filter(anulado=False)
        usados = consumos_dia.count()
        if usados >= cupo:
            return ResultadoConsumo(consumos_dia.order_by("-numero").first(), False, usados, cupo)

        # El número siguiente se toma del máximo existente (no del conteo) para que un
        # hueco en la numeración no provoque una colisión y un falso «cupo agotado».
        ultimo_numero = todos_dia.aggregate(maximo=Max("numero"))["maximo"] or 0
        # El consumo queda en el local de quien escanea (operador o administrador).
        local = local_de_usuario(operador)
        try:
            with transaction.atomic():
                consumo = Consumo.objects.create(
                    trabajador=trabajador,
                    fecha=fecha,
                    numero=ultimo_numero + 1,
                    operador=operador,
                    local=local,
                    metodo=metodo,
                )
        except IntegrityError:
            existente = consumos_dia.order_by("-numero").first()
            if existente is None:
                raise
            return ResultadoConsumo(existente, False, consumos_dia.count(), cupo)

        return ResultadoConsumo(consumo, True, usados + 1, cupo)


class AnulacionInvalida(Exception):
    """La anulación no se puede realizar; el mensaje explica por qué."""


def anular_consumo(consumo_id, usuario, motivo):
    """Anula un consumo: deja de contar para el cupo y no se cobra.

    Solo un administrador puede anular y el motivo es obligatorio. El registro se
    conserva (nunca se borra) con quién, cuándo y por qué se anuló.
    """
    if not (usuario.is_authenticated and usuario.is_staff):
        raise PermissionDenied("Solo un administrador puede anular consumos.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise AnulacionInvalida("El motivo de la anulación es obligatorio.")

    trabajador_id = Consumo.objects.filter(pk=consumo_id).values_list("trabajador_id", flat=True).first()
    if trabajador_id is None:
        raise AnulacionInvalida("El consumo no existe.")
    with transaction.atomic():
        # Mismo orden de bloqueo que el registro (trabajador primero) para evitar deadlocks.
        Trabajador.objects.select_for_update().filter(pk=trabajador_id).first()
        consumo = Consumo.objects.select_for_update().get(pk=consumo_id)
        if consumo.anulado:
            raise AnulacionInvalida("El consumo ya estaba anulado.")
        consumo.anulado = True
        consumo.anulado_por = usuario
        consumo.anulado_en = timezone.now()
        consumo.motivo_anulacion = motivo[:200]
        consumo.save(update_fields=["anulado", "anulado_por", "anulado_en", "motivo_anulacion"])
    return consumo
