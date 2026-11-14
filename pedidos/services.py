from django.db import transaction
from django.utils import timezone

from consumos.services import PedidoRechazado, _mover_porcion
from menus.models import Acompanamiento, MovimientoPorcion, PlatoDia, ReservaPorcion
from menus.services import disponible
from trabajadores.models import Trabajador

from .models import Pedido, PedidoItem


def cambiar_plato(item_id, nuevo_plato_id, nuevo_acompanamiento_id, usuario, motivo=""):
    """Cambia el plato (o el acompañamiento) de una línea de un pedido Pendiente.

    Devuelve la porción anterior y toma la nueva, con movimientos de tipo «cambio».
    Bloqueos en el orden fijo: trabajador → platos por id → acompañamientos por id → pedido.
    """
    linea = (
        PedidoItem.objects.select_related("pedido__consumo", "plato")
        .filter(pk=item_id)
        .first()
    )
    if linea is None:
        raise PedidoRechazado("pedido_invalido", "La línea del pedido no existe.")
    pedido_id = linea.pedido_id
    trabajador_id = linea.pedido.consumo.trabajador_id
    try:
        nuevo_plato_id = int(nuevo_plato_id)
        nuevo_acompanamiento_id = int(nuevo_acompanamiento_id) if nuevo_acompanamiento_id not in (None, "") else None
    except (TypeError, ValueError):
        raise PedidoRechazado("seleccion_incompleta", "La selección no es válida.")

    with transaction.atomic():
        Trabajador.objects.select_for_update().filter(pk=trabajador_id).first()
        plato_ids = sorted({linea.plato_id, nuevo_plato_id})
        acomp_ids = sorted({a for a in (linea.acompanamiento_id, nuevo_acompanamiento_id) if a})
        platos = {p.pk: p for p in PlatoDia.objects.select_for_update().filter(pk__in=plato_ids).order_by("id")}
        acomps = {a.pk: a for a in Acompanamiento.objects.select_for_update().filter(pk__in=acomp_ids).order_by("id")}
        pedido = Pedido.objects.select_for_update().select_related("consumo").get(pk=pedido_id)
        linea = PedidoItem.objects.get(pk=item_id)

        if pedido.estado != Pedido.PENDIENTE or pedido.consumo.anulado:
            raise PedidoRechazado("pedido_no_pendiente", "Solo se puede cambiar el plato de un pedido Pendiente.")
        anterior = platos[linea.plato_id]
        nuevo = platos.get(nuevo_plato_id)
        if nuevo is None or nuevo.menu_id != anterior.menu_id or nuevo.tiempo_id != anterior.tiempo_id:
            raise PedidoRechazado("seleccion_incompleta", f"El nuevo plato debe ser de {linea.tiempo_nombre} del mismo menú.")
        nuevo_acomp = acomps.get(nuevo_acompanamiento_id) if nuevo_acompanamiento_id else None
        if nuevo_acompanamiento_id and (nuevo_acomp is None or nuevo_acomp.plato_id != nuevo.pk):
            raise PedidoRechazado("seleccion_incompleta", "El acompañamiento no corresponde al plato.")
        if nuevo_acomp is None and nuevo.acompanamientos.exists():
            raise PedidoRechazado("seleccion_incompleta", f"Falta elegir el acompañamiento de {nuevo.nombre}.", nuevo.nombre)
        anterior_acomp = acomps.get(linea.acompanamiento_id) if linea.acompanamiento_id else None
        if nuevo == anterior and nuevo_acomp == anterior_acomp:
            return linea

        ahora = timezone.now()
        cambios = []
        if nuevo != anterior:
            cambios.append((anterior, nuevo, "plato"))
        if nuevo_acomp != anterior_acomp:
            cambios.append((anterior_acomp, nuevo_acomp, "acompanamiento"))
        for _, entra, campo in cambios:
            if entra is None:
                continue
            reservadas = ReservaPorcion.objects.filter(**{campo: entra}, expira_en__gt=ahora).count()
            if disponible(entra, reservadas) == 0:
                raise PedidoRechazado("porcion_agotada", f"{entra.nombre}: agotado.", entra.nombre)

        motivo = (motivo or "Cambio de plato").strip()[:200]
        for sale, entra, _ in cambios:
            if sale is not None:
                _mover_porcion(sale, usuario, MovimientoPorcion.TIPO_CAMBIO, 1, pedido, motivo)
            if entra is not None:
                _mover_porcion(entra, usuario, MovimientoPorcion.TIPO_CAMBIO, -1, pedido, motivo)

        linea.plato = nuevo
        linea.plato_nombre = nuevo.nombre
        linea.acompanamiento = nuevo_acomp
        linea.acompanamiento_nombre = nuevo_acomp.nombre if nuevo_acomp else ""
        linea.save(update_fields=["plato", "plato_nombre", "acompanamiento", "acompanamiento_nombre"])
    return linea
