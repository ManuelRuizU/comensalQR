from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction

from operadores.models import local_de_usuario

from .models import Mesa


class MesaInvalida(Exception):
    """El QR de mesa no se acepta. `codigo` es estable para el cliente."""

    def __init__(self, codigo, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _exigir_admin(usuario):
    if not (usuario.is_authenticated and usuario.is_staff):
        raise PermissionDenied("Solo un administrador puede gestionar las mesas.")


def mesa_valida(mesa, local):
    """Una mesa se acepta solo si existe, está activa y es del local de quien escanea."""
    if mesa is None:
        raise MesaInvalida("mesa_invalida", "QR de mesa no válido.")
    if local is None or mesa.local_id != local.pk:
        raise MesaInvalida("mesa_invalida", f"{mesa.nombre} no pertenece a tu local.")
    if not mesa.activa:
        raise MesaInvalida("mesa_invalida", f"{mesa.nombre} está desactivada.")
    return mesa


def identificar_mesa(token, usuario):
    """Mesa del QR escaneado, validada contra el local del garzón."""
    mesa = Mesa.objects.select_related("local").filter(token=(token or "").strip()).first()
    return mesa_valida(mesa, local_de_usuario(usuario))


def crear_mesa(usuario, local, nombre):
    _exigir_admin(usuario)
    nombre = (nombre or "").strip()
    if not nombre:
        raise MesaInvalida("nombre_obligatorio", "Indica el nombre de la mesa.")
    try:
        with transaction.atomic():
            return Mesa.objects.create(local=local, nombre=nombre[:30])
    except IntegrityError:
        raise MesaInvalida("nombre_repetido", f"Ya existe «{nombre}» en este local.")


def cambiar_estado(usuario, mesa, activa):
    _exigir_admin(usuario)
    mesa.activa = activa
    mesa.save(update_fields=["activa"])
    return mesa
