"""Escenario común para las pruebas de menú y pedidos (no es código de producción)."""

import uuid

from django.contrib.auth import get_user_model
from django.utils import timezone

from empresas.models import Empresa
from locales.models import Local
from operadores.models import Administrador, Operador
from trabajadores.models import Trabajador

from .models import Acompanamiento, MenuDia, PlatoDia, TiempoMenu


def crear_escenario(porciones_chuleta=30, porciones_pure=15, porciones_arroz=15, cupo=1, publicado=True):
    User = get_user_model()
    local = Local.objects.create(nombre="Restaurante de Prueba", direccion="Calle 1")
    admin = User.objects.create_user(username="admin@prueba.cl", password="x", is_staff=True)
    Administrador.objects.create(usuario=admin, local=local)
    garzon_a = User.objects.create_user(username="garzon.a", password="x")
    Operador.objects.create(usuario=garzon_a, local=local)
    garzon_b = User.objects.create_user(username="garzon.b", password="x")
    Operador.objects.create(usuario=garzon_b, local=local)
    empresa = Empresa.objects.create(
        nombre="Constructora ABC", rut="76111111-6", direccion="Dir", encargado_personal="RRHH",
        almuerzos_diarios=cupo,
    )
    trabajador = Trabajador.objects.create(nombre="Javier", apellido="Cid", rut="11111111-1", empresa=empresa)
    otro = Trabajador.objects.create(nombre="Ana", apellido="Soto", rut="22222222-2", empresa=empresa)

    fondo = TiempoMenu.objects.get(nombre="Fondo")
    postre = TiempoMenu.objects.get(nombre="Postre")
    menu = MenuDia.objects.create(local=local, fecha=timezone.localdate(), publicado=publicado)
    chuleta = PlatoDia.objects.create(menu=menu, tiempo=fondo, nombre="Chuleta de cerdo", porciones=porciones_chuleta)
    pure = Acompanamiento.objects.create(plato=chuleta, nombre="Puré", porciones=porciones_pure)
    arroz = Acompanamiento.objects.create(plato=chuleta, nombre="Arroz", porciones=porciones_arroz)
    pollo = PlatoDia.objects.create(menu=menu, tiempo=fondo, nombre="Pollo asado", porciones=10)
    naranja = PlatoDia.objects.create(menu=menu, tiempo=postre, nombre="Naranja", porciones=None)

    class E:
        pass

    e = E()
    e.__dict__.update(locals())
    return e


def nuevo_token():
    return uuid.uuid4()
