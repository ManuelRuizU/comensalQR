"""Punto único de escritura de consumos.

Todo consumo, por QR o manual, con o sin menú, se crea aquí:
- registrar_consumo_diario(): días sin menú publicado (comportamiento v0.1).
- registrar_pedido(): con menú publicado; el consumo nace junto con su pedido.

Ambos comparten el mismo núcleo (bloquear trabajador, validar cupo, crear consumo).
Orden fijo de bloqueos en toda escritura: trabajador → platos por id →
acompañamientos por id → consumo/pedido → FolioDiario.
"""

import uuid
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from menus.models import Acompanamiento, MenuDia, MovimientoPorcion, PlatoDia, ReservaPorcion, TiempoMenu
from menus.services import disponible
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


# --- Núcleo compartido -------------------------------------------------------------------

def _bloquear_trabajador(trabajador_id):
    """Bloquea la fila del trabajador: serializa los registros del mismo QR y el conteo del cupo."""
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
    return trabajador


@dataclass
class _Cupo:
    todos_dia: object
    vigentes_dia: object
    usados: int
    cupo: int

    @property
    def agotado(self):
        return self.usados >= self.cupo


def _cupo_del_dia(trabajador, fecha):
    # Los anulados no cuentan para el cupo, pero su número no se reutiliza.
    todos = Consumo.objects.filter(trabajador=trabajador, fecha=fecha)
    vigentes = todos.filter(anulado=False)
    return _Cupo(todos, vigentes, vigentes.count(), trabajador.cupo_diario)


def _crear_consumo(trabajador, operador, fecha, metodo, cupo):
    # El número siguiente se toma del máximo existente (no del conteo) para que un
    # hueco en la numeración no provoque una colisión y un falso «cupo agotado».
    ultimo_numero = cupo.todos_dia.aggregate(maximo=Max("numero"))["maximo"] or 0
    return Consumo.objects.create(
        trabajador=trabajador,
        fecha=fecha,
        numero=ultimo_numero + 1,
        operador=operador,
        # El consumo queda en el local de quien escanea (operador o administrador).
        local=local_de_usuario(operador),
        metodo=metodo,
    )


def estado_cupo(trabajador_id, fecha=None):
    """Consulta sin bloqueo para avisar al escanear; la verificación real ocurre al confirmar."""
    trabajador = Trabajador.objects.select_related("empresa").filter(pk=trabajador_id).first()
    if (
        trabajador is None
        or not trabajador.activo
        or trabajador.eliminado_en is not None
        or not trabajador.empresa.activa
    ):
        raise TrabajadorNoDisponible
    cupo = _cupo_del_dia(trabajador, fecha or timezone.localdate())
    return trabajador, cupo.usados, cupo.cupo


# --- v0.1: registro sin menú -------------------------------------------------------------

def registrar_consumo_diario(trabajador_id, operador, fecha=None, metodo=Consumo.METODO_QR):
    """Registra un almuerzo sin pedido (día sin menú publicado).

    Si el cupo está agotado devuelve el último consumo del día con creado=False.
    """
    fecha = fecha or timezone.localdate()
    with transaction.atomic():
        trabajador = _bloquear_trabajador(trabajador_id)
        cupo = _cupo_del_dia(trabajador, fecha)
        if cupo.agotado:
            return ResultadoConsumo(cupo.vigentes_dia.order_by("-numero").first(), False, cupo.usados, cupo.cupo)
        try:
            with transaction.atomic():
                consumo = _crear_consumo(trabajador, operador, fecha, metodo, cupo)
        except IntegrityError:
            existente = cupo.vigentes_dia.order_by("-numero").first()
            if existente is None:
                raise
            return ResultadoConsumo(existente, False, cupo.vigentes_dia.count(), cupo.cupo)
        return ResultadoConsumo(consumo, True, cupo.usados + 1, cupo.cupo)


# --- v0.2: registro con pedido -----------------------------------------------------------

class PedidoRechazado(Exception):
    """El pedido no se creó. Nada quedó escrito. `codigo` es estable para el cliente."""

    def __init__(self, codigo, mensaje, item=None, usados=None, cupo=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.item = item
        self.usados = usados
        self.cupo = cupo


@dataclass
class ResultadoPedido:
    pedido: object
    creado: bool
    usados: int
    cupo: int
    items: list = field(default_factory=list)

    @property
    def consumo(self):
        return self.pedido.consumo


def _resultado_existente(pedido):
    trabajador = pedido.consumo.trabajador
    cupo = _cupo_del_dia(trabajador, pedido.fecha)
    return ResultadoPedido(pedido, False, cupo.usados, cupo.cupo, list(pedido.items.all()))


def _normalizar_seleccion(seleccion):
    """[{"plato": id, "acompanamiento": id|None}, ...] → lista de pares de enteros."""
    pares = []
    for linea in seleccion or []:
        try:
            plato = int(linea.get("plato"))
            acomp = linea.get("acompanamiento")
            acomp = int(acomp) if acomp not in (None, "") else None
        except (TypeError, ValueError, AttributeError):
            raise PedidoRechazado("seleccion_incompleta", "La selección no es válida.")
        pares.append((plato, acomp))
    return pares


def _bloquear_items_seleccion(menu, pares):
    """Bloquea los platos y luego los acompañamientos, cada grupo ordenado por id."""
    plato_ids = sorted({p for p, _ in pares})
    acomp_ids = sorted({a for _, a in pares if a})
    platos = {
        p.pk: p
        for p in PlatoDia.objects.select_for_update()
        .filter(pk__in=plato_ids, menu=menu)
        .order_by("id")
    }
    acomps = {
        a.pk: a
        for a in Acompanamiento.objects.select_for_update()
        .filter(pk__in=acomp_ids, plato__menu=menu)
        .order_by("id")
    }
    return platos, acomps


def _validar_seleccion(menu, pares, platos, acomps):
    """Un ítem por tiempo, todos los tiempos obligatorios cubiertos, acompañamiento si corresponde."""
    tiempos = {t.pk: t for t in TiempoMenu.objects.filter(activo=True)}
    elegidos = {}
    lineas = []
    for plato_id, acomp_id in pares:
        plato = platos.get(plato_id)
        if plato is None or plato.tiempo_id not in tiempos:
            raise PedidoRechazado("seleccion_incompleta", "Un plato elegido no está en el menú de hoy.")
        if plato.tiempo_id in elegidos:
            raise PedidoRechazado(
                "seleccion_incompleta", f"Solo se puede elegir una opción de {tiempos[plato.tiempo_id].nombre}."
            )
        elegidos[plato.tiempo_id] = plato
        acomp = None
        if acomp_id:
            acomp = acomps.get(acomp_id)
            if acomp is None or acomp.plato_id != plato.pk:
                raise PedidoRechazado("seleccion_incompleta", "Un acompañamiento no corresponde a su plato.")
        elif plato.acompanamientos.exists():
            raise PedidoRechazado(
                "seleccion_incompleta", f"Falta elegir el acompañamiento de {plato.nombre}.", plato.nombre
            )
        lineas.append((tiempos[plato.tiempo_id], plato, acomp))

    con_platos = set(menu.platos.values_list("tiempo_id", flat=True))
    faltantes = [
        t.nombre for t in tiempos.values()
        if t.obligatorio and t.pk in con_platos and t.pk not in elegidos
    ]
    if faltantes:
        raise PedidoRechazado("seleccion_incompleta", "Falta elegir: " + ", ".join(faltantes) + ".")
    if not lineas:
        raise PedidoRechazado("seleccion_incompleta", "Elige al menos un plato.")
    return sorted(lineas, key=lambda linea: (linea[0].orden, linea[1].pk))


def _validar_porciones(lineas, token, ahora):
    """Disponible + reservas propias ≥ 1, es decir: porciones − vendidas − reservas ajenas ≥ 1."""
    for _, plato, acomp in lineas:
        for item, campo in ((plato, "plato"), (acomp, "acompanamiento")):
            if item is None:
                continue
            ajenas = (
                ReservaPorcion.objects.filter(**{campo: item}, expira_en__gt=ahora)
                .exclude(token_seleccion=token)
                .count()
            )
            if disponible(item, ajenas) == 0:
                raise PedidoRechazado("porcion_agotada", f"{item.nombre}: agotado.", item.nombre)


def _siguiente_folio(local, fecha):
    from pedidos.models import FolioDiario

    try:
        with transaction.atomic():
            FolioDiario.objects.get_or_create(local=local, fecha=fecha)
    except IntegrityError:
        pass  # otro pedido lo creó al mismo tiempo; se bloquea abajo
    folio = FolioDiario.objects.select_for_update().get(local=local, fecha=fecha)
    folio.ultimo += 1
    folio.save(update_fields=["ultimo"])
    return folio.ultimo


def _mover_porcion(item, usuario, tipo, cantidad, pedido, motivo=""):
    """Actualiza vendidas (el ítem ya está bloqueado) y deja el movimiento registrado."""
    item.vendidas = max(0, item.vendidas - cantidad)  # cantidad −1 = se vende una
    item.save(update_fields=["vendidas"])
    campo = "plato" if isinstance(item, PlatoDia) else "acompanamiento"
    MovimientoPorcion.objects.create(
        **{campo: item}, tipo=tipo, cantidad=cantidad, usuario=usuario, pedido=pedido, motivo=motivo
    )


def registrar_pedido(trabajador_id, operador, token, seleccion, metodo=Consumo.METODO_QR, fecha=None):
    """Confirma el pedido de un comensal: consumo + pedido + folio + ítems + movimientos.

    Todo en una sola transacción; cualquier rechazo revierte todo (PedidoRechazado).
    Idempotente: el mismo `token` (token_seleccion) devuelve el mismo pedido sin crear otro.
    """
    from pedidos.models import Pedido, PedidoItem

    try:
        token = uuid.UUID(str(token))
    except ValueError:
        raise PedidoRechazado("seleccion_incompleta", "Falta el identificador de la selección.")
    existente = Pedido.objects.filter(clave_idempotencia=token).first()
    if existente is not None:
        return _resultado_existente(existente)

    fecha = fecha or timezone.localdate()
    local = local_de_usuario(operador)
    pares = _normalizar_seleccion(seleccion)
    ahora = timezone.now()
    try:
        with transaction.atomic():
            try:
                trabajador = _bloquear_trabajador(trabajador_id)
            except TrabajadorNoDisponible:
                raise PedidoRechazado("qr_invalido", "Trabajador inactivo o desvinculado. No puede registrar almuerzos.")
            # Un doble clic que llegó mientras el primero tenía el bloqueo encuentra su pedido aquí.
            existente = Pedido.objects.filter(clave_idempotencia=token).first()
            if existente is not None:
                return _resultado_existente(existente)

            cupo = _cupo_del_dia(trabajador, fecha)
            if cupo.agotado:
                raise PedidoRechazado(
                    "cupo_agotado", f"Cupo diario agotado ({cupo.usados} de {cupo.cupo}).",
                    usados=cupo.usados, cupo=cupo.cupo,
                )
            menu = MenuDia.objects.filter(local=local, fecha=fecha, publicado=True).first() if local else None
            if menu is None:
                raise PedidoRechazado("menu_no_publicado", "No hay menú publicado hoy en tu local.")

            platos, acomps = _bloquear_items_seleccion(menu, pares)
            lineas = _validar_seleccion(menu, pares, platos, acomps)
            _validar_porciones(lineas, token, ahora)

            consumo = _crear_consumo(trabajador, operador, fecha, metodo, cupo)
            pedido = Pedido.objects.create(
                consumo=consumo,
                local=local,
                fecha=fecha,
                folio=_siguiente_folio(local, fecha),
                clave_idempotencia=token,
            )
            items = []
            for tiempo, plato, acomp in lineas:
                items.append(PedidoItem.objects.create(
                    pedido=pedido,
                    tiempo_nombre=tiempo.nombre,
                    plato=plato,
                    plato_nombre=plato.nombre,
                    acompanamiento=acomp,
                    acompanamiento_nombre=acomp.nombre if acomp else "",
                ))
                _mover_porcion(plato, operador, MovimientoPorcion.TIPO_PEDIDO, -1, pedido)
                if acomp:
                    _mover_porcion(acomp, operador, MovimientoPorcion.TIPO_PEDIDO, -1, pedido)
            ReservaPorcion.objects.filter(token_seleccion=token).delete()
    except IntegrityError:
        # Carrera en la clave de idempotencia: el otro intento ya creó el pedido.
        existente = Pedido.objects.filter(clave_idempotencia=token).first()
        if existente is None:
            raise
        return _resultado_existente(existente)
    return ResultadoPedido(pedido, True, cupo.usados + 1, cupo.cupo, items)


# --- Anulación ----------------------------------------------------------------------------

class AnulacionInvalida(Exception):
    """La anulación no se puede realizar; el mensaje explica por qué."""


def anular_consumo(consumo_id, usuario, motivo):
    """Anula un consumo: deja de contar para el cupo y no se cobra.

    Solo un administrador puede anular y el motivo es obligatorio. El registro se
    conserva (nunca se borra) con quién, cuándo y por qué se anuló. Si el consumo
    tiene pedido, el pedido queda Anulado y sus porciones vuelven al disponible.
    """
    from pedidos.models import Pedido, PedidoItem

    if not (usuario.is_authenticated and usuario.is_staff):
        raise PermissionDenied("Solo un administrador puede anular consumos.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise AnulacionInvalida("El motivo de la anulación es obligatorio.")

    trabajador_id = Consumo.objects.filter(pk=consumo_id).values_list("trabajador_id", flat=True).first()
    if trabajador_id is None:
        raise AnulacionInvalida("El consumo no existe.")
    lineas = list(PedidoItem.objects.filter(pedido__consumo_id=consumo_id).values_list("plato_id", "acompanamiento_id"))
    with transaction.atomic():
        # Mismo orden de bloqueo que el registro: trabajador → platos → acompañamientos → consumo.
        Trabajador.objects.select_for_update().filter(pk=trabajador_id).first()
        platos = {p.pk: p for p in PlatoDia.objects.select_for_update().filter(pk__in=[p for p, _ in lineas]).order_by("id")}
        acomps = {a.pk: a for a in Acompanamiento.objects.select_for_update().filter(pk__in=[a for _, a in lineas if a]).order_by("id")}
        consumo = Consumo.objects.select_for_update().get(pk=consumo_id)
        if consumo.anulado:
            raise AnulacionInvalida("El consumo ya estaba anulado.")
        consumo.anulado = True
        consumo.anulado_por = usuario
        consumo.anulado_en = timezone.now()
        consumo.motivo_anulacion = motivo[:200]
        consumo.save(update_fields=["anulado", "anulado_por", "anulado_en", "motivo_anulacion"])

        pedido = Pedido.objects.select_for_update().filter(consumo=consumo).first()
        if pedido is not None:
            for item in pedido.items.all():
                _mover_porcion(platos[item.plato_id], usuario, MovimientoPorcion.TIPO_ANULACION, 1, pedido, motivo[:200])
                if item.acompanamiento_id:
                    _mover_porcion(
                        acomps[item.acompanamiento_id], usuario, MovimientoPorcion.TIPO_ANULACION, 1, pedido, motivo[:200]
                    )
            pedido.estado = Pedido.ANULADO
            pedido.save(update_fields=["estado"])
    return consumo
