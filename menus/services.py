"""Reglas del menú del día: disponibilidad, reservas temporales y movimientos de porciones.

La reserva solo mejora la experiencia del garzón. La garantía de que una porción
no se vende dos veces es la transacción de confirmación (consumos.services.registrar_pedido).
"""

from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from operadores.models import local_de_usuario

from .models import Acompanamiento, MenuDia, MovimientoPorcion, PlatoDia, ReservaPorcion, TiempoMenu


DURACION_RESERVA = timedelta(seconds=90)


class ErrorMenu(Exception):
    """Operación del menú rechazada. `codigo` es estable para el cliente; el texto es para mostrar."""

    def __init__(self, codigo, mensaje, item=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.item = item


# --- Consultas -----------------------------------------------------------------------

def menu_publicado(local, fecha=None):
    """Menú publicado del local para la fecha (hoy por defecto), o None."""
    if local is None:
        return None
    fecha = fecha or timezone.localdate()
    return MenuDia.objects.filter(local=local, fecha=fecha, publicado=True).first()


def menu_publicado_de_usuario(usuario, fecha=None):
    return menu_publicado(local_de_usuario(usuario), fecha)


def _reservas_vigentes(ahora=None):
    return ReservaPorcion.objects.filter(expira_en__gt=ahora or timezone.now())


def disponible(item, reservadas):
    """Porciones que se pueden vender: porciones − vendidas − reservas vigentes.

    None = sin límite. Un ítem marcado Agotado tiene 0.
    """
    if item.agotado:
        return 0
    if item.porciones is None:
        return None
    return max(0, item.porciones - item.vendidas - reservadas)


def _estado(item, quedan, reservadas_ajenas):
    if item.agotado:
        return "agotado"
    if quedan is None:
        return "disponible"
    if quedan <= 0:
        return "reservada_por_otro" if reservadas_ajenas else "agotado"
    if item.umbral_aviso is not None and quedan <= item.umbral_aviso:
        return "bajo"
    return "disponible"


def disponibilidad(menu, token=None, ahora=None):
    """Estado de cada ítem del menú para mostrar en el escáner, la administración y el polling.

    Las reservas del propio `token` (el comensal que el garzón está atendiendo) no se
    descuentan: para ese garzón esas porciones siguen siendo suyas.
    """
    vigentes = _reservas_vigentes(ahora).filter(plato__menu=menu)
    propias = Q(token_seleccion=token) if token else Q(pk__in=[])
    por_plato = {
        fila["plato_id"]: fila
        for fila in vigentes.values("plato_id").annotate(
            total=Count("id"), propias=Count("id", filter=propias)
        )
    }
    por_acomp = {
        fila["acompanamiento_id"]: fila
        for fila in vigentes.exclude(acompanamiento=None).values("acompanamiento_id").annotate(
            total=Count("id"), propias=Count("id", filter=propias)
        )
    }

    def describir(item, conteo):
        total = conteo["total"] if conteo else 0
        mias = conteo["propias"] if conteo else 0
        ajenas = total - mias
        quedan = disponible(item, ajenas)
        return {
            "id": item.pk,
            "nombre": item.nombre,
            "porciones": item.porciones,
            "vendidas": item.vendidas,
            "reservadas": total,
            "quedan": quedan,
            "estado": _estado(item, quedan, ajenas),
            "agotado_manual": item.agotado,
            "umbral": item.umbral_aviso,
        }

    tiempos = []
    platos = (
        menu.platos.select_related("tiempo")
        .prefetch_related("acompanamientos")
        .filter(tiempo__activo=True)
        .order_by("tiempo__orden", "orden", "id")
    )
    actual = None
    for plato in platos:
        if actual is None or actual["id"] != plato.tiempo_id:
            actual = {
                "id": plato.tiempo_id,
                "nombre": plato.tiempo.nombre,
                "obligatorio": plato.tiempo.obligatorio,
                "platos": [],
            }
            tiempos.append(actual)
        datos = describir(plato, por_plato.get(plato.pk))
        acomps = [describir(a, por_acomp.get(a.pk)) for a in plato.acompanamientos.all()]
        datos["acompanamientos"] = acomps
        if acomps and datos["estado"] != "agotado" and all(a["estado"] in ("agotado", "reservada_por_otro") for a in acomps):
            # Sin ningún acompañamiento disponible, el plato tampoco se puede pedir.
            datos["estado"] = "reservada_por_otro" if any(a["estado"] == "reservada_por_otro" for a in acomps) else "agotado"
        actual["platos"].append(datos)
    return {"menu_id": menu.pk, "fecha": menu.fecha.isoformat(), "tiempos": tiempos}


# --- Reservas --------------------------------------------------------------------------

def _bloquear_items(plato_id, acompanamiento_id, menu):
    """Bloquea plato y acompañamiento en el orden fijo: platos antes que acompañamientos."""
    plato = PlatoDia.objects.select_for_update().select_related("tiempo").filter(pk=plato_id, menu=menu).first()
    if plato is None:
        raise ErrorMenu("seleccion_incompleta", "Ese plato no está en el menú de hoy.")
    acomp = None
    if acompanamiento_id:
        acomp = Acompanamiento.objects.select_for_update().filter(pk=acompanamiento_id, plato=plato).first()
        if acomp is None:
            raise ErrorMenu("seleccion_incompleta", "Ese acompañamiento no corresponde al plato.")
    elif plato.acompanamientos.exists():
        raise ErrorMenu("seleccion_incompleta", f"Elige un acompañamiento para {plato.nombre}.", plato.nombre)
    return plato, acomp


def renovar_reservas(operador, token, ahora=None):
    """Extiende 90 s desde ahora las reservas vigentes de este comensal y este garzón.

    Se llama en cada interacción del garzón con la hoja. Las ya vencidas no se
    reviven: si el garzón deja de interactuar, vencen como siempre.
    """
    ahora = ahora or timezone.now()
    return ReservaPorcion.objects.filter(
        token_seleccion=token, operador=operador, expira_en__gt=ahora
    ).update(expira_en=ahora + DURACION_RESERVA)


def reservar(operador, token, plato_id, acompanamiento_id=None):
    """Reserva 1 porción del plato (y su acompañamiento) por 90 s para el comensal `token`.

    Si el mismo comensal ya tenía una reserva en ese tiempo, se libera (cambio de opción).
    Tocar una opción es una interacción: renueva las demás reservas del comensal,
    aunque la opción tocada resulte agotada.
    """
    menu = menu_publicado_de_usuario(operador)
    if menu is None:
        raise ErrorMenu("menu_no_publicado", "No hay menú publicado hoy en tu local.")
    ahora = timezone.now()
    renovar_reservas(operador, token, ahora)
    with transaction.atomic():
        plato, acomp = _bloquear_items(plato_id, acompanamiento_id, menu)
        ReservaPorcion.objects.filter(token_seleccion=token, plato__tiempo=plato.tiempo).delete()
        ReservaPorcion.objects.filter(expira_en__lte=ahora).filter(
            Q(plato=plato) | Q(acompanamiento=acomp) if acomp else Q(plato=plato)
        ).delete()

        for item, campo in ((plato, "plato"), (acomp, "acompanamiento")):
            if item is None:
                continue
            reservadas = ReservaPorcion.objects.filter(**{campo: item}, expira_en__gt=ahora).count()
            if disponible(item, reservadas) == 0:
                if not item.agotado and reservadas:
                    raise ErrorMenu(
                        "reservada_por_otro",
                        f"{item.nombre}: agotado (reservada por otro garzón).",
                        item.nombre,
                    )
                raise ErrorMenu("porcion_agotada", f"{item.nombre}: agotado.", item.nombre)

        ReservaPorcion.objects.create(
            plato=plato,
            acompanamiento=acomp,
            operador=operador,
            token_seleccion=token,
            expira_en=ahora + DURACION_RESERVA,
        )
    return {"plato": plato.pk, "acompanamiento": acomp.pk if acomp else None, "expira_en": (ahora + DURACION_RESERVA).isoformat()}


def liberar(operador, token, tiempo_id=None):
    """Libera las reservas del comensal (todas, o solo las de un tiempo).

    Quitar la opción de un tiempo es una interacción: renueva las reservas restantes.
    """
    reservas = ReservaPorcion.objects.filter(token_seleccion=token, operador=operador)
    if tiempo_id:
        reservas = reservas.filter(plato__tiempo_id=tiempo_id)
    eliminadas, _ = reservas.delete()
    if tiempo_id:
        renovar_reservas(operador, token)
    return eliminadas


# --- Administración de porciones --------------------------------------------------------

def _exigir_admin(usuario):
    if not (usuario.is_authenticated and usuario.is_staff):
        raise PermissionDenied("Solo un administrador puede modificar el menú.")


def _modelo_item(tipo):
    return {"plato": PlatoDia, "acompanamiento": Acompanamiento}[tipo]


def registrar_carga(item, usuario, cantidad, motivo="Carga inicial"):
    """Movimiento de carga al definir o cambiar porciones antes de publicar."""
    if cantidad:
        campo = "plato" if isinstance(item, PlatoDia) else "acompanamiento"
        MovimientoPorcion.objects.create(
            **{campo: item}, tipo=MovimientoPorcion.TIPO_CARGA, cantidad=cantidad, usuario=usuario, motivo=motivo
        )


def ajustar_porciones(tipo, item_id, nuevas_porciones, usuario, motivo):
    """Cambia las porciones cargadas de un ítem a mitad de servicio. Exige motivo."""
    _exigir_admin(usuario)
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErrorMenu("motivo_obligatorio", "El motivo del ajuste es obligatorio.")
    with transaction.atomic():
        item = _modelo_item(tipo).objects.select_for_update().get(pk=item_id)
        if item.porciones is None:
            raise ErrorMenu("sin_limite", f"{item.nombre} no tiene límite de porciones.")
        if nuevas_porciones < item.vendidas:
            raise ErrorMenu(
                "ajuste_invalido",
                f"{item.nombre} ya vendió {item.vendidas}; no puede quedar con menos porciones.",
            )
        diferencia = nuevas_porciones - item.porciones
        if diferencia == 0:
            return item
        item.porciones = nuevas_porciones
        item.save(update_fields=["porciones"])
        campo = "plato" if tipo == "plato" else "acompanamiento"
        MovimientoPorcion.objects.create(
            **{campo: item}, tipo=MovimientoPorcion.TIPO_AJUSTE, cantidad=diferencia, usuario=usuario, motivo=motivo[:200]
        )
    return item


def marcar_agotado(tipo, item_id, agotado, usuario):
    _exigir_admin(usuario)
    with transaction.atomic():
        item = _modelo_item(tipo).objects.select_for_update().get(pk=item_id)
        item.agotado = agotado
        item.save(update_fields=["agotado"])
    return item


def copiar_menu(origen, fecha, usuario):
    """Crea el menú de `fecha` (sin publicar) copiando platos, acompañamientos y porciones."""
    _exigir_admin(usuario)
    with transaction.atomic():
        if MenuDia.objects.filter(local=origen.local, fecha=fecha).exists():
            raise ErrorMenu("menu_existente", "Ya existe un menú para ese día; edítalo en lugar de copiar.")
        nuevo = MenuDia.objects.create(local=origen.local, fecha=fecha)
        for plato in origen.platos.prefetch_related("acompanamientos"):
            copia = PlatoDia.objects.create(
                menu=nuevo, tiempo=plato.tiempo, nombre=plato.nombre, porciones=plato.porciones,
                umbral_aviso=plato.umbral_aviso, orden=plato.orden,
            )
            registrar_carga(copia, usuario, plato.porciones, f"Copia del menú del {origen.fecha:%d-%m-%Y}")
            for acomp in plato.acompanamientos.all():
                copia_acomp = Acompanamiento.objects.create(
                    plato=copia, nombre=acomp.nombre, porciones=acomp.porciones,
                    umbral_aviso=acomp.umbral_aviso, orden=acomp.orden,
                )
                registrar_carga(copia_acomp, usuario, acomp.porciones, f"Copia del menú del {origen.fecha:%d-%m-%Y}")
    return nuevo


def publicar(menu, publicado, usuario):
    _exigir_admin(usuario)
    if publicado:
        obligatorios = TiempoMenu.objects.filter(activo=True, obligatorio=True)
        faltantes = [t.nombre for t in obligatorios if not menu.platos.filter(tiempo=t).exists()]
        if faltantes:
            raise ErrorMenu(
                "menu_incompleto", "Falta al menos un plato en: " + ", ".join(faltantes) + "."
            )
    menu.publicado = publicado
    menu.save(update_fields=["publicado"])
    return menu


def ultima_seleccion(operador, fecha=None):
    """Platos del último pedido vigente de este garzón hoy («Igual al anterior»)."""
    from pedidos.models import Pedido

    pedido = (
        Pedido.objects.filter(consumo__operador=operador, fecha=fecha or timezone.localdate())
        .exclude(estado=Pedido.ANULADO)
        .order_by("-creado", "-id")
        .prefetch_related("items")
        .first()
    )
    if pedido is None:
        return []
    return [{"plato": i.plato_id, "acompanamiento": i.acompanamiento_id} for i in pedido.items.all()]


@dataclass
class ResumenItem:
    nombre: str
    tiempo: str
    cargadas: int
    ajustes: int
    servidas: int
    anuladas: int
    quedan: object
    sin_limite: bool


def informe_cierre(menu):
    """Porciones por ítem a partir de los movimientos: cargadas, ajustes, servidas, anuladas, quedan."""
    def sumar(movs, tipo):
        return sum(m.cantidad for m in movs if m.tipo == tipo)

    filas = []
    for plato in menu.platos.select_related("tiempo").prefetch_related("movimientos", "acompanamientos__movimientos"):
        for item, nombre in [(plato, plato.nombre)] + [(a, f"{plato.nombre} + {a.nombre}") for a in plato.acompanamientos.all()]:
            movs = list(item.movimientos.all())
            # «servidas» = pedidos menos cambios devueltos; un cambio suma +1 al ítem que se deja.
            servidas = -(sumar(movs, MovimientoPorcion.TIPO_PEDIDO) + sumar(movs, MovimientoPorcion.TIPO_CAMBIO))
            filas.append(ResumenItem(
                nombre=nombre if item is plato else f"↳ {item.nombre}",
                tiempo=plato.tiempo.nombre,
                cargadas=sumar(movs, MovimientoPorcion.TIPO_CARGA),
                ajustes=sumar(movs, MovimientoPorcion.TIPO_AJUSTE),
                servidas=servidas,
                anuladas=sumar(movs, MovimientoPorcion.TIPO_ANULACION),
                quedan=None if item.porciones is None else item.porciones - item.vendidas,
                sin_limite=item.porciones is None,
            ))
    return filas


# --- Edición de ítems -------------------------------------------------------------------

def crear_item(usuario, menu, nombre, porciones, umbral_aviso, tiempo=None, plato=None):
    """Agrega un plato (con `tiempo`) o un acompañamiento (con `plato`) y registra la carga."""
    _exigir_admin(usuario)
    with transaction.atomic():
        if plato is not None:
            item = Acompanamiento.objects.create(
                plato=plato, nombre=nombre, porciones=porciones, umbral_aviso=umbral_aviso,
                orden=plato.acompanamientos.count(),
            )
        else:
            item = PlatoDia.objects.create(
                menu=menu, tiempo=tiempo, nombre=nombre, porciones=porciones, umbral_aviso=umbral_aviso,
                orden=menu.platos.filter(tiempo=tiempo).count(),
            )
        registrar_carga(item, usuario, porciones)
    return item


def editar_item(usuario, tipo, item_id, nombre, umbral_aviso, porciones=None, cambiar_porciones=False):
    """Edita nombre y umbral. Las porciones solo se editan aquí antes de publicar el menú;
    después se usan ajustes con motivo."""
    _exigir_admin(usuario)
    with transaction.atomic():
        item = _modelo_item(tipo).objects.select_for_update().get(pk=item_id)
        menu = item.menu if tipo == "plato" else item.plato.menu
        item.nombre = nombre
        item.umbral_aviso = umbral_aviso
        campos = ["nombre", "umbral_aviso"]
        if cambiar_porciones:
            if menu.publicado:
                raise ErrorMenu("menu_publicado", "El menú está publicado: usa «Ajustar» e indica el motivo.")
            if porciones is not None and porciones < item.vendidas:
                raise ErrorMenu("ajuste_invalido", f"{item.nombre} ya vendió {item.vendidas}.")
            # La suma de cargas siempre iguala las porciones (sin límite cuenta como 0).
            registrar_carga(item, usuario, (porciones or 0) - (item.porciones or 0), "Corrección de carga")
            item.porciones = porciones
            campos.append("porciones")
        item.save(update_fields=campos)
    return item


def eliminar_item(usuario, tipo, item_id):
    """Elimina un ítem de un menú NO publicado que nunca se vendió ni se pidió.

    Con el menú publicado solo se ajustan porciones (con motivo) o se marca Agotado.
    Los movimientos de carga del ítem se van con él.
    """
    _exigir_admin(usuario)
    with transaction.atomic():
        item = _modelo_item(tipo).objects.select_for_update().get(pk=item_id)
        menu = item.menu if tipo == "plato" else item.plato.menu
        if menu.publicado:
            raise ErrorMenu(
                "menu_publicado",
                f"El menú está publicado: no se puede eliminar {item.nombre}. Ajusta sus porciones o márcalo Agotado.",
            )
        if item.vendidas or item.pedido_items.exists() or item.movimientos.exclude(tipo=MovimientoPorcion.TIPO_CARGA).exists():
            raise ErrorMenu("item_con_ventas", f"{item.nombre} ya tiene pedidos: márcalo Agotado en lugar de eliminarlo.")
        if tipo == "plato":
            if MovimientoPorcion.objects.filter(acompanamiento__plato=item).exclude(tipo=MovimientoPorcion.TIPO_CARGA).exists():
                raise ErrorMenu("item_con_ventas", f"{item.nombre} ya tiene pedidos: márcalo Agotado.")
            MovimientoPorcion.objects.filter(acompanamiento__plato=item).delete()
        item.movimientos.all().delete()
        item.delete()
