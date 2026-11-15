import json
import threading
import unittest
from datetime import timedelta
from unittest.mock import patch

from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from consumos.models import Consumo
from consumos.services import PedidoRechazado, anular_consumo
from consumos.services import registrar_pedido as _registrar_pedido
from menus import services as menu
from menus.escenario_prueba import crear_escenario, nuevo_token
from menus.models import MovimientoPorcion, ReservaPorcion

from . import despacho
from .models import FolioDiario, Pedido
from .services import cambiar_plato


def registrar_pedido(*args, **kwargs):
    """En el local la mesa es obligatoria: por defecto se usa la mesa del escenario (la
    primera mesa activa del local de quien registra). Solo las pruebas de despacho pasan
    `despacho=True`, y las de mesa pasan `mesa_id` explícitamente."""
    if "mesa_id" not in kwargs and not kwargs.get("despacho"):
        from mesas.models import Mesa
        from operadores.models import local_de_usuario

        mesa = Mesa.objects.filter(local=local_de_usuario(args[1]), activa=True).order_by("id").first()
        kwargs["mesa_id"] = mesa.pk if mesa else None
    return _registrar_pedido(*args, **kwargs)


def chuleta_con(e, acomp):
    return {"plato": e.chuleta.pk, "acompanamiento": acomp.pk}


class ReservaTests(TestCase):
    def setUp(self):
        self.e = crear_escenario(porciones_pure=1)

    def test_reserva_vencida_devuelve_la_porcion(self):
        token = nuevo_token()
        menu.reservar(self.e.garzon_a, token, self.e.chuleta.pk, self.e.pure.pk)
        with self.assertRaises(menu.ErrorMenu) as error:
            menu.reservar(self.e.garzon_b, nuevo_token(), self.e.chuleta.pk, self.e.pure.pk)
        self.assertEqual(error.exception.codigo, "reservada_por_otro")

        ReservaPorcion.objects.update(expira_en=timezone.now() - timedelta(seconds=1))

        menu.reservar(self.e.garzon_b, nuevo_token(), self.e.chuleta.pk, self.e.pure.pk)
        self.assertEqual(ReservaPorcion.objects.count(), 1)

    def test_cambiar_de_opcion_libera_la_reserva_anterior(self):
        token = nuevo_token()
        menu.reservar(self.e.garzon_a, token, self.e.chuleta.pk, self.e.pure.pk)
        menu.reservar(self.e.garzon_a, token, self.e.chuleta.pk, self.e.arroz.pk)

        self.assertEqual(ReservaPorcion.objects.get(token_seleccion=token).acompanamiento, self.e.arroz)
        menu.reservar(self.e.garzon_b, nuevo_token(), self.e.chuleta.pk, self.e.pure.pk)  # el puré quedó libre

    def test_disponibilidad_muestra_reservada_por_otro_y_propias(self):
        token = nuevo_token()
        menu.reservar(self.e.garzon_a, token, self.e.chuleta.pk, self.e.pure.pk)

        def pure(estado):
            fondo = next(t for t in estado["tiempos"] if t["nombre"] == "Fondo")
            chuleta = next(p for p in fondo["platos"] if p["id"] == self.e.chuleta.pk)
            return next(a for a in chuleta["acompanamientos"] if a["id"] == self.e.pure.pk)

        self.assertEqual(pure(menu.disponibilidad(self.e.menu))["estado"], "reservada_por_otro")
        self.assertEqual(pure(menu.disponibilidad(self.e.menu, token=token))["quedan"], 1)

    def test_cancelar_libera_todas(self):
        token = nuevo_token()
        menu.reservar(self.e.garzon_a, token, self.e.chuleta.pk, self.e.pure.pk)
        menu.reservar(self.e.garzon_a, token, self.e.naranja.pk)

        self.assertEqual(menu.liberar(self.e.garzon_a, token), 2)
        self.assertFalse(ReservaPorcion.objects.exists())

    def en(self, segundos):
        """Fija el reloj en t0 + segundos (t0 = inicio de la prueba)."""
        return patch("django.utils.timezone.now", return_value=self.t0 + timedelta(seconds=segundos))

    def reservar_pure_ajeno(self):
        menu.reservar(self.e.garzon_b, nuevo_token(), self.e.chuleta.pk, self.e.pure.pk)

    def test_cada_interaccion_renueva_las_reservas_del_comensal(self):
        self.t0 = timezone.now()
        token = nuevo_token()
        with self.en(0):
            menu.reservar(self.e.garzon_a, token, self.e.chuleta.pk, self.e.pure.pk)  # vence en t0+90
        with self.en(60):
            menu.reservar(self.e.garzon_a, token, self.e.naranja.pk)  # interacción: todo vence en t0+150
        self.assertEqual(
            set(ReservaPorcion.objects.filter(token_seleccion=token).values_list("expira_en", flat=True)),
            {self.t0 + timedelta(seconds=150)},
        )
        with self.en(120), self.assertRaises(menu.ErrorMenu) as error:
            self.reservar_pure_ajeno()  # sin renovación habría vencido en t0+90
        self.assertEqual(error.exception.codigo, "reservada_por_otro")
        with self.en(151):
            self.reservar_pure_ajeno()  # el garzón dejó de interactuar: venció igual que antes

    def test_quitar_un_tiempo_y_tocar_una_opcion_agotada_tambien_renuevan(self):
        self.t0 = timezone.now()
        token = nuevo_token()
        menu.marcar_agotado("plato", self.e.pollo.pk, True, self.e.admin)
        with self.en(0):
            menu.reservar(self.e.garzon_a, token, self.e.chuleta.pk, self.e.pure.pk)
            menu.reservar(self.e.garzon_a, token, self.e.naranja.pk)
        with self.en(50), self.assertRaises(menu.ErrorMenu):
            menu.reservar(self.e.garzon_a, token, self.e.pollo.pk)  # agotado, pero renueva hasta t0+140
        with self.en(100):
            menu.liberar(self.e.garzon_a, token, tiempo_id=self.e.naranja.tiempo_id)  # renueva hasta t0+190
        reserva = ReservaPorcion.objects.get(token_seleccion=token)
        self.assertEqual((reserva.plato, reserva.expira_en), (self.e.chuleta, self.t0 + timedelta(seconds=190)))

    def test_sin_interaccion_vencen_y_renovar_no_revive_las_vencidas(self):
        self.t0 = timezone.now()
        token = nuevo_token()
        with self.en(0):
            menu.reservar(self.e.garzon_a, token, self.e.chuleta.pk, self.e.pure.pk)
        with self.en(91):
            self.assertEqual(menu.renovar_reservas(self.e.garzon_a, token), 0)
            self.reservar_pure_ajeno()

    def test_endpoint_renovar_solo_toca_las_reservas_propias(self):
        self.t0 = timezone.now()
        mio, ajeno = nuevo_token(), nuevo_token()
        with self.en(0):
            menu.reservar(self.e.garzon_a, mio, self.e.chuleta.pk, self.e.arroz.pk)
            menu.reservar(self.e.garzon_b, ajeno, self.e.pollo.pk)
        self.client.force_login(self.e.garzon_a)
        with self.en(30):
            respuesta = self.client.post(reverse("consumos:renovar"), {"selection_token": str(mio)})
        self.assertEqual(respuesta.json(), {"ok": True, "renewed": 1})
        self.assertEqual(ReservaPorcion.objects.get(token_seleccion=mio).expira_en, self.t0 + timedelta(seconds=120))
        self.assertEqual(ReservaPorcion.objects.get(token_seleccion=ajeno).expira_en, self.t0 + timedelta(seconds=90))

    def test_plato_con_acompanamientos_exige_uno(self):
        with self.assertRaises(menu.ErrorMenu) as error:
            menu.reservar(self.e.garzon_a, nuevo_token(), self.e.chuleta.pk)
        self.assertEqual(error.exception.codigo, "seleccion_incompleta")


class RegistrarPedidoTests(TestCase):
    def setUp(self):
        self.e = crear_escenario()

    def pedir(self, seleccion, garzon=None, trabajador=None, token=None):
        return registrar_pedido(
            (trabajador or self.e.trabajador).pk, garzon or self.e.garzon_a, token or nuevo_token(), seleccion
        )

    def test_confirmar_crea_consumo_pedido_folio_items_y_movimientos(self):
        token = nuevo_token()
        menu.reservar(self.e.garzon_a, token, self.e.chuleta.pk, self.e.arroz.pk)

        resultado = self.pedir([chuleta_con(self.e, self.e.arroz), {"plato": self.e.naranja.pk}], token=token)

        pedido = resultado.pedido
        self.assertTrue(resultado.creado)
        self.assertEqual((pedido.folio, pedido.estado, pedido.mesa_nombre), (1, "pendiente", "Mesa 1"))
        self.assertEqual(pedido.consumo.local, self.e.local)
        self.assertEqual([str(i) for i in pedido.items.all()], ["Chuleta de cerdo + Arroz", "Naranja"])
        self.e.chuleta.refresh_from_db(); self.e.arroz.refresh_from_db(); self.e.naranja.refresh_from_db()
        self.assertEqual((self.e.chuleta.vendidas, self.e.arroz.vendidas, self.e.naranja.vendidas), (1, 1, 1))
        self.assertEqual(MovimientoPorcion.objects.filter(pedido=pedido, tipo="pedido", cantidad=-1).count(), 3)
        self.assertFalse(ReservaPorcion.objects.exists())

    def test_idempotencia_mismo_token_un_solo_pedido(self):
        token = nuevo_token()
        primero = self.pedir([chuleta_con(self.e, self.e.arroz)], token=token)
        segundo = self.pedir([chuleta_con(self.e, self.e.arroz)], token=token)

        self.assertFalse(segundo.creado)
        self.assertEqual(primero.pedido.pk, segundo.pedido.pk)
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(Consumo.objects.count(), 1)

    def test_combinacion_sin_stock_de_acompanamiento(self):
        self.e.pure.porciones = 0
        self.e.pure.save()

        with self.assertRaises(PedidoRechazado) as error:
            self.pedir([chuleta_con(self.e, self.e.pure)])
        self.assertEqual((error.exception.codigo, error.exception.item), ("porcion_agotada", "Puré"))
        self.assertFalse(Consumo.objects.exists())
        # La chuleta sigue disponible con arroz.
        self.assertTrue(self.pedir([chuleta_con(self.e, self.e.arroz)]).creado)

    def test_tiempo_obligatorio_faltante(self):
        with self.assertRaises(PedidoRechazado) as error:
            self.pedir([{"plato": self.e.naranja.pk}])
        self.assertEqual(error.exception.codigo, "seleccion_incompleta")
        self.assertIn("Fondo", error.exception.mensaje)
        self.assertFalse(Consumo.objects.exists())

    def test_falta_acompanamiento_o_dos_opciones_del_mismo_tiempo(self):
        for seleccion in (
            [{"plato": self.e.chuleta.pk}],
            [chuleta_con(self.e, self.e.arroz), {"plato": self.e.pollo.pk}],
        ):
            with self.assertRaises(PedidoRechazado) as error:
                self.pedir(seleccion)
            self.assertEqual(error.exception.codigo, "seleccion_incompleta")

    def test_cupo_agotado_no_crea_nada(self):
        self.pedir([{"plato": self.e.pollo.pk}])
        with self.assertRaises(PedidoRechazado) as error:
            self.pedir([{"plato": self.e.pollo.pk}])
        self.assertEqual(error.exception.codigo, "cupo_agotado")
        self.assertEqual(Pedido.objects.count(), 1)
        self.e.pollo.refresh_from_db()
        self.assertEqual(self.e.pollo.vendidas, 1)

    def test_sin_menu_publicado(self):
        self.e.menu.publicado = False
        self.e.menu.save()
        with self.assertRaises(PedidoRechazado) as error:
            self.pedir([{"plato": self.e.pollo.pk}])
        self.assertEqual(error.exception.codigo, "menu_no_publicado")

    def test_porcion_reservada_por_otro_no_se_puede_confirmar(self):
        self.e.pollo.porciones = 1
        self.e.pollo.save()
        menu.reservar(self.e.garzon_b, nuevo_token(), self.e.pollo.pk)

        with self.assertRaises(PedidoRechazado) as error:
            self.pedir([{"plato": self.e.pollo.pk}])
        self.assertEqual(error.exception.codigo, "porcion_agotada")

    def test_agotado_manual(self):
        menu.marcar_agotado("plato", self.e.pollo.pk, True, self.e.admin)
        with self.assertRaises(PedidoRechazado):
            self.pedir([{"plato": self.e.pollo.pk}])

    def test_folio_correlativo_por_local_y_dia_sin_reutilizar_anulados(self):
        primero = self.pedir([{"plato": self.e.pollo.pk}])
        anular_consumo(primero.consumo.pk, self.e.admin, "Error de digitación")
        segundo = self.pedir([{"plato": self.e.pollo.pk}])
        tercero = self.pedir([{"plato": self.e.pollo.pk}], trabajador=self.e.otro)

        self.assertEqual([primero.pedido.folio, segundo.pedido.folio, tercero.pedido.folio], [1, 2, 3])
        self.assertEqual(FolioDiario.objects.get().ultimo, 3)


class AnulacionYCambioTests(TestCase):
    def setUp(self):
        self.e = crear_escenario()
        self.resultado = registrar_pedido(
            self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [chuleta_con(self.e, self.e.pure)]
        )

    def recargar(self):
        for item in (self.e.chuleta, self.e.pure, self.e.arroz, self.e.pollo):
            item.refresh_from_db()

    def test_anulado_no_cuenta_para_el_cupo_y_devuelve_la_porcion(self):
        anular_consumo(self.resultado.consumo.pk, self.e.admin, "El comensal no almorzó")

        self.recargar()
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.estado, Pedido.ANULADO)
        self.assertEqual((self.e.chuleta.vendidas, self.e.pure.vendidas), (0, 0))
        self.assertEqual(MovimientoPorcion.objects.filter(tipo="anulacion", cantidad=1).count(), 2)
        # Con cupo 1, puede volver a pedir.
        nuevo = registrar_pedido(self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}])
        self.assertTrue(nuevo.creado)
        self.assertEqual(nuevo.usados, 1)

    def test_cambio_de_plato_mueve_porciones(self):
        linea = self.resultado.pedido.items.get()
        cambiar_plato(linea.pk, self.e.chuleta.pk, self.e.arroz.pk, self.e.admin)
        self.recargar()
        self.assertEqual((self.e.chuleta.vendidas, self.e.pure.vendidas, self.e.arroz.vendidas), (1, 0, 1))

        cambiar_plato(linea.pk, self.e.pollo.pk, None, self.e.admin)
        self.recargar()
        self.assertEqual((self.e.chuleta.vendidas, self.e.arroz.vendidas, self.e.pollo.vendidas), (0, 0, 1))
        linea.refresh_from_db()
        self.assertEqual((linea.plato_nombre, linea.acompanamiento_nombre), ("Pollo asado", ""))
        filas = {f.nombre: f for f in menu.informe_cierre(self.e.menu)}
        self.assertEqual((filas["Chuleta de cerdo"].servidas, filas["Pollo asado"].servidas), (0, 1))

    def test_cambio_solo_en_pendiente(self):
        Pedido.objects.update(estado=Pedido.LISTO)
        with self.assertRaises(PedidoRechazado) as error:
            cambiar_plato(self.resultado.pedido.items.get().pk, self.e.pollo.pk, None, self.e.admin)
        self.assertEqual(error.exception.codigo, "pedido_no_pendiente")

    def test_informe_cierre(self):
        menu.ajustar_porciones("plato", self.e.chuleta.pk, 35, self.e.admin, "Llegó más carne")
        filas = {f.nombre: f for f in menu.informe_cierre(self.e.menu)}
        chuleta = filas["Chuleta de cerdo"]
        self.assertEqual((chuleta.ajustes, chuleta.servidas, chuleta.quedan), (5, 1, 34))


@unittest.skipUnless(connection.vendor == "postgresql", "Requiere PostgreSQL real (bloqueo de filas).")
class ConcurrenciaPostgresTests(TransactionTestCase):
    """Dos garzones confirmando a la vez: la transacción con bloqueo de filas decide."""

    def setUp(self):
        # TransactionTestCase vacía las tablas entre pruebas: se recrean los tiempos iniciales.
        from menus.models import TiempoMenu

        TiempoMenu.objects.get_or_create(nombre="Fondo", defaults={"orden": 1, "obligatorio": True})
        TiempoMenu.objects.get_or_create(nombre="Postre", defaults={"orden": 3, "obligatorio": False})

    def _en_paralelo(self, tareas):
        barrera = threading.Barrier(len(tareas))
        resultados = [None] * len(tareas)

        def correr(i, tarea):
            try:
                barrera.wait()
                resultados[i] = tarea()
            except Exception as error:  # noqa: BLE001 - se inspecciona en la prueba
                resultados[i] = error
            finally:
                connections.close_all()

        hilos = [threading.Thread(target=correr, args=(i, t)) for i, t in enumerate(tareas)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        return resultados

    def test_ultima_porcion_se_vende_una_sola_vez(self):
        e = crear_escenario()
        e.pollo.porciones = 1
        e.pollo.save()

        resultados = self._en_paralelo([
            lambda: registrar_pedido(e.trabajador.pk, e.garzon_a, nuevo_token(), [{"plato": e.pollo.pk}]),
            lambda: registrar_pedido(e.otro.pk, e.garzon_b, nuevo_token(), [{"plato": e.pollo.pk}]),
        ])

        creados = [r for r in resultados if not isinstance(r, Exception)]
        rechazos = [r for r in resultados if isinstance(r, PedidoRechazado)]
        self.assertEqual((len(creados), len(rechazos)), (1, 1), resultados)
        self.assertEqual(rechazos[0].codigo, "porcion_agotada")
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(Consumo.objects.count(), 1)
        e.pollo.refresh_from_db()
        self.assertEqual(e.pollo.vendidas, 1)

    def test_folios_sin_saltos_ni_repetidos_bajo_concurrencia(self):
        e = crear_escenario(cupo=10)
        tareas = [
            (lambda: registrar_pedido(e.trabajador.pk, e.garzon_a, nuevo_token(), [{"plato": e.pollo.pk}])),
            (lambda: registrar_pedido(e.otro.pk, e.garzon_b, nuevo_token(), [{"plato": e.pollo.pk}])),
        ] * 3

        resultados = self._en_paralelo(tareas)

        self.assertFalse([r for r in resultados if isinstance(r, Exception)], resultados)
        folios = sorted(Pedido.objects.values_list("folio", flat=True))
        self.assertEqual(folios, [1, 2, 3, 4, 5, 6])

    def test_doble_clic_simultaneo_crea_un_solo_pedido(self):
        e = crear_escenario()
        token = nuevo_token()
        resultados = self._en_paralelo([
            lambda: registrar_pedido(e.trabajador.pk, e.garzon_a, token, [{"plato": e.pollo.pk}]),
        ] * 2)

        self.assertFalse([r for r in resultados if isinstance(r, Exception)], resultados)
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(len({r.pedido.pk for r in resultados}), 1)


class EscanerConMenuTests(TestCase):
    def setUp(self):
        self.e = crear_escenario()
        self.client.force_login(self.e.garzon_a)

    def escanear(self, **campos):
        # El escáner envía siempre la mesa activa: aquí, la del escenario.
        datos = {"mesa_id": self.e.mesa.pk, **campos}
        return self.client.post(reverse("consumos:escaner"), datos, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def qr(self):
        return {"token": str(self.e.trabajador.token_qr)}

    def confirmar(self, token, seleccion, **campos):
        return self.client.post(
            reverse("consumos:confirmar"),
            {"mesa_id": self.e.mesa.pk, **(campos or self.qr()), "selection_token": token, "seleccion": json.dumps(seleccion)},
        )

    def test_escanear_abre_la_hoja_sin_registrar_nada(self):
        datos = self.escanear(**self.qr()).json()

        self.assertEqual(datos["status"], "seleccion")
        self.assertEqual((datos["worker"], datos["used"], datos["quota"]), ("Javier Cid", 0, 1))
        self.assertEqual([t["nombre"] for t in datos["menu"]["tiempos"]], ["Fondo", "Postre"])
        self.assertFalse(Consumo.objects.exists())

    def test_reservar_confirmar_y_resultado_con_folio(self):
        token = self.escanear(**self.qr()).json()["selection_token"]
        reserva = self.client.post(reverse("consumos:reservar"), {"selection_token": token, "plato": self.e.chuleta.pk, "acompanamiento": self.e.arroz.pk})
        self.assertEqual(reserva.status_code, 200)

        datos = self.confirmar(token, [chuleta_con(self.e, self.e.arroz)]).json()

        self.assertEqual((datos["status"], datos["folio"], datos["message"]), ("registered", "0001", "Pedido 0001 · Mesa 1"))
        self.assertEqual(datos["items"], ["Chuleta de cerdo + Arroz"])
        self.assertEqual(Pedido.objects.get().consumo.metodo, Consumo.METODO_QR)
        # Reintento de red con la misma selección: mismo pedido, sin crear otro.
        self.assertEqual(self.confirmar(token, [chuleta_con(self.e, self.e.arroz)]).json()["folio"], "0001")
        self.assertEqual(Pedido.objects.count(), 1)

    def test_reserva_ajena_responde_reservada_por_otro(self):
        self.e.pollo.porciones = 1
        self.e.pollo.save()
        menu.reservar(self.e.garzon_b, nuevo_token(), self.e.pollo.pk)

        respuesta = self.client.post(reverse("consumos:reservar"), {"selection_token": str(nuevo_token()), "plato": self.e.pollo.pk})

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["code"], "reservada_por_otro")

    def test_porcion_agotada_al_confirmar_mantiene_la_hoja(self):
        self.e.pollo.porciones = 0
        self.e.pollo.save()

        respuesta = self.confirmar(str(nuevo_token()), [{"plato": self.e.pollo.pk}])

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual((respuesta.json()["code"], respuesta.json()["item"]), ("porcion_agotada", "Pollo asado"))
        self.assertFalse(Consumo.objects.exists())

    def test_registro_manual_por_rut_usa_la_misma_hoja(self):
        manual = {"trabajador_id": str(self.e.trabajador.pk)}
        datos = self.escanear(**manual).json()
        self.assertEqual((datos["status"], datos["manual"]), ("seleccion", True))

        resultado = self.confirmar(datos["selection_token"], [{"plato": self.e.pollo.pk}], **manual).json()

        self.assertEqual(resultado["status"], "registered")
        self.assertEqual(Pedido.objects.get().consumo.metodo, Consumo.METODO_RUT)

    def test_cupo_agotado_al_escanear(self):
        registrar_pedido(self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}])

        datos = self.escanear(**self.qr()).json()

        self.assertEqual(datos["status"], "duplicate")
        self.assertEqual(datos["message"], "Cupo diario agotado (1 de 1).")

    def test_igual_al_anterior(self):
        registrar_pedido(self.e.otro.pk, self.e.garzon_a, nuevo_token(), [chuleta_con(self.e, self.e.pure), {"plato": self.e.naranja.pk}])

        datos = self.escanear(**self.qr()).json()

        self.assertEqual(
            datos["previous"],
            [{"plato": self.e.chuleta.pk, "acompanamiento": self.e.pure.pk}, {"plato": self.e.naranja.pk, "acompanamiento": None}],
        )

    def test_sin_menu_publicado_registra_directo_con_la_mesa(self):
        self.e.menu.publicado = False
        self.e.menu.save()

        datos = self.escanear(**self.qr()).json()

        self.assertEqual((datos["status"], datos["message"]), ("registered", "Almuerzo 1 de 1 registrado."))
        consumo = Consumo.objects.get()
        self.assertFalse(Pedido.objects.exists())
        self.assertEqual((consumo.local, consumo.mesa), (self.e.local, self.e.mesa))
        self.assertEqual(self.escanear(**self.qr()).json()["status"], "duplicate")

    def test_usuario_sin_local_no_registra_porque_no_tiene_mesas(self):
        from django.contrib.auth import get_user_model

        sin_local = get_user_model().objects.create_user(username="root", password="x", is_staff=True)
        self.client.force_login(sin_local)

        respuesta = self.escanear(**self.qr())  # la mesa del escenario no es de su local
        self.assertEqual((respuesta.status_code, respuesta.json()["code"]), (409, "mesa_invalida"))
        self.assertFalse(Consumo.objects.exists())

    def test_disponibilidad_de_hoy_con_etag(self):
        url = reverse("menus:disponibilidad_hoy")
        primera = self.client.get(url)
        self.assertEqual(primera.json()["menu_id"], self.e.menu.pk)
        self.assertEqual(self.client.get(url, HTTP_IF_NONE_MATCH=primera["ETag"]).status_code, 304)
        menu.reservar(self.e.garzon_b, nuevo_token(), self.e.pollo.pk)
        self.assertEqual(self.client.get(url, HTTP_IF_NONE_MATCH=primera["ETag"]).status_code, 200)


class PedidosDelDiaTests(TestCase):
    def setUp(self):
        self.e = crear_escenario()
        self.resultado = registrar_pedido(
            self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [chuleta_con(self.e, self.e.pure)]
        )
        self.client.force_login(self.e.admin)

    def test_lista_muestra_folio_platos_y_opciones_de_cambio(self):
        response = self.client.get(reverse("pedidos:lista"))

        self.assertContains(response, "0001")
        self.assertContains(response, "Chuleta de cerdo + Puré")
        self.assertContains(response, "Pollo asado")  # opción de cambio del mismo tiempo

    def test_cambiar_plato_desde_la_pantalla(self):
        item = self.resultado.pedido.items.get()
        self.client.post(reverse("pedidos:cambiar_item", args=[item.pk]), {"opcion": f"{self.e.pollo.pk}:"})

        item.refresh_from_db()
        self.assertEqual(item.plato_nombre, "Pollo asado")

    def test_anular_exige_motivo_y_devuelve_porciones(self):
        url = reverse("consumos:anular", args=[self.resultado.consumo.pk])
        self.client.post(url, {"motivo": ""})
        self.assertFalse(Consumo.objects.get().anulado)

        self.client.post(url, {"motivo": "No almorzó"})

        self.assertTrue(Consumo.objects.get().anulado)
        self.assertEqual(Pedido.objects.get().estado, Pedido.ANULADO)
        self.e.pure.refresh_from_db()
        self.assertEqual(self.e.pure.vendidas, 0)

    def test_garzon_no_anula_ni_cambia(self):
        self.client.force_login(self.e.garzon_a)
        item = self.resultado.pedido.items.get()

        self.client.post(reverse("consumos:anular", args=[self.resultado.consumo.pk]), {"motivo": "x"})
        self.client.post(reverse("pedidos:cambiar_item", args=[item.pk]), {"opcion": f"{self.e.pollo.pk}:"})

        self.assertFalse(Consumo.objects.get().anulado)
        item.refresh_from_db()
        self.assertEqual(item.plato_nombre, "Chuleta de cerdo")
        self.assertEqual(self.client.get(reverse("pedidos:lista")).status_code, 302)

    def test_anular_consumo_sin_pedido_desde_el_historial(self):
        self.e.menu.publicado = False
        self.e.menu.save()
        from consumos.services import registrar_consumo_diario

        consumo = registrar_consumo_diario(self.e.otro.pk, self.e.garzon_a).consumo
        historial = self.client.get(reverse("consumos:historial"))
        self.assertContains(historial, reverse("consumos:anular", args=[consumo.pk]))

        self.client.post(reverse("consumos:anular", args=[consumo.pk]), {"motivo": "Prueba"})

        consumo.refresh_from_db()
        self.assertTrue(consumo.anulado)


class MesaEnPedidoTests(TestCase):
    def setUp(self):
        from locales.models import Local
        from mesas.models import Mesa

        self.e = crear_escenario()
        self.mesa = Mesa.objects.create(local=self.e.local, nombre="Mesa 3")
        otro_local = Local.objects.create(nombre="Otro local", direccion="Calle 9")
        self.mesa_ajena = Mesa.objects.create(local=otro_local, nombre="Mesa 3")

    def pedir(self, mesa_id):
        return registrar_pedido(
            self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}], mesa_id=mesa_id
        )

    def test_el_pedido_guarda_la_mesa_activa(self):
        pedido = self.pedir(self.mesa.pk).pedido

        self.assertEqual((pedido.mesa, pedido.mesa_nombre), (self.mesa, "Mesa 3"))
        # Renombrar la mesa después no altera el historial del pedido.
        self.mesa.nombre = "Terraza 1"
        self.mesa.save()
        pedido.refresh_from_db()
        self.assertEqual(pedido.mesa_nombre, "Mesa 3")

    def test_despacho_solo_con_administrador(self):
        for pedir in (
            lambda: _registrar_pedido(self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}], despacho=True),
        ):
            with self.assertRaises(PedidoRechazado) as error:
                pedir()
            self.assertEqual(error.exception.codigo, "despacho_no_permitido")
        self.assertFalse(Consumo.objects.exists())

        pedido = _registrar_pedido(
            self.e.trabajador.pk, self.e.admin, nuevo_token(), [{"plato": self.e.pollo.pk}], despacho=True
        ).pedido
        self.assertIsNone(pedido.mesa)
        self.assertIsNone(pedido.consumo.mesa)
        self.assertTrue(pedido.es_despacho)
        self.assertEqual(pedido.mesa_nombre, "Despacho · Constructora ABC")

    def test_la_regla_aplica_tambien_al_administrador(self):
        with self.assertRaises(PedidoRechazado) as error:
            _registrar_pedido(self.e.trabajador.pk, self.e.admin, nuevo_token(), [{"plato": self.e.pollo.pk}])
        self.assertEqual(error.exception.codigo, "mesa_obligatoria")

    def test_mesa_inactiva_o_de_otro_local_se_rechaza_sin_crear_nada(self):
        self.mesa.activa = False
        self.mesa.save()
        for mesa_id in (self.mesa.pk, self.mesa_ajena.pk, 999999, "x"):
            with self.assertRaises(PedidoRechazado) as error:
                self.pedir(mesa_id)
            self.assertEqual(error.exception.codigo, "mesa_invalida")
        self.assertFalse(Consumo.objects.exists())
        self.assertFalse(FolioDiario.objects.exists())
        self.e.pollo.refresh_from_db()
        self.assertEqual(self.e.pollo.vendidas, 0)


class EscanerModoMesaTests(TestCase):
    def setUp(self):
        from locales.models import Local
        from mesas.models import Mesa

        self.e = crear_escenario()
        self.mesa = Mesa.objects.create(local=self.e.local, nombre="Mesa 3")
        self.inactiva = Mesa.objects.create(local=self.e.local, nombre="Mesa 4", activa=False)
        self.ajena = Mesa.objects.create(local=Local.objects.create(nombre="Otro", direccion="X"), nombre="Mesa 1")
        self.client.force_login(self.e.garzon_a)

    def escanear(self, contenido, **modo):
        return self.client.post(
            reverse("consumos:escaner"), {"token": contenido, **modo}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

    def test_comensal_sin_mesa_no_abre_la_hoja_ni_registra(self):
        for publicado in (True, False):  # con y sin menú
            self.e.menu.publicado = publicado
            self.e.menu.save()
            for campos in ({"token": str(self.e.trabajador.token_qr)}, {"trabajador_id": str(self.e.trabajador.pk)}):
                respuesta = self.client.post(reverse("consumos:escaner"), campos, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
                self.assertEqual(respuesta.status_code, 409)
                self.assertEqual(
                    (respuesta.json()["status"], respuesta.json()["message"]), ("sin_mesa", "Escanea primero la mesa.")
                )
        self.assertFalse(ReservaPorcion.objects.exists())
        self.assertFalse(Consumo.objects.exists())

    def test_confirmar_sin_mesa_ni_despacho_se_rechaza(self):
        respuesta = self.client.post(reverse("consumos:confirmar"), {
            "token": str(self.e.trabajador.token_qr), "selection_token": str(nuevo_token()),
            "seleccion": json.dumps([{"plato": self.e.pollo.pk}]),
        })
        self.assertEqual((respuesta.status_code, respuesta.json()["code"]), (409, "mesa_obligatoria"))
        self.assertFalse(Pedido.objects.exists())

    def test_el_escaner_no_acepta_despacho(self):
        # Un garzón no puede saltarse la mesa pidiendo «despacho»: el escáner ignora ese campo.
        respuesta = self.client.post(reverse("consumos:confirmar"), {
            "trabajador_id": str(self.e.trabajador.pk), "despacho": "1", "selection_token": str(nuevo_token()),
            "seleccion": json.dumps([{"plato": self.e.pollo.pk}]),
        })
        self.assertEqual((respuesta.status_code, respuesta.json()["code"]), (409, "mesa_obligatoria"))
        self.assertFalse(Pedido.objects.exists())

    def test_escanear_comensal_con_mesa_inactiva_no_abre_la_hoja(self):
        respuesta = self.escanear(str(self.e.trabajador.token_qr), mesa_id=self.inactiva.pk)
        self.assertEqual((respuesta.status_code, respuesta.json()["code"]), (409, "mesa_invalida"))

    def test_escanear_mesa_activa_el_modo_mesa(self):
        datos = self.escanear(self.mesa.token).json()

        self.assertEqual((datos["status"], datos["table_id"], datos["table"]), ("mesa", self.mesa.pk, "Mesa 3"))
        self.assertFalse(Consumo.objects.exists())

    def test_qr_de_mesa_inactiva_o_de_otro_local_es_rechazado(self):
        for mesa, motivo in ((self.inactiva, "desactivada"), (self.ajena, "no pertenece a tu local")):
            respuesta = self.escanear(mesa.token)
            self.assertEqual(respuesta.status_code, 400)
            self.assertEqual(respuesta.json()["code"], "mesa_invalida")
            self.assertIn(motivo, respuesta.json()["message"])

    def test_qr_que_no_es_trabajador_ni_mesa_sigue_siendo_invalido(self):
        respuesta = self.escanear("cualquier-cosa")
        self.assertEqual((respuesta.status_code, respuesta.json()["message"]), (400, "QR no válido."))

    def test_confirmar_guarda_la_mesa_activa_y_el_resultado_la_muestra(self):
        datos = self.escanear(str(self.e.trabajador.token_qr), mesa_id=self.mesa.pk).json()
        respuesta = self.client.post(reverse("consumos:confirmar"), {
            "token": str(self.e.trabajador.token_qr), "selection_token": datos["selection_token"],
            "seleccion": json.dumps([{"plato": self.e.pollo.pk}]), "mesa_id": self.mesa.pk,
        }).json()

        self.assertEqual(respuesta["message"], "Pedido 0001 · Mesa 3")
        self.assertEqual(Pedido.objects.get().mesa, self.mesa)

    def test_confirmar_con_mesa_desactivada_entre_medio_no_crea_nada(self):
        datos = self.escanear(str(self.e.trabajador.token_qr), mesa_id=self.mesa.pk).json()
        self.mesa.activa = False
        self.mesa.save()
        respuesta = self.client.post(reverse("consumos:confirmar"), {
            "token": str(self.e.trabajador.token_qr), "selection_token": datos["selection_token"],
            "seleccion": json.dumps([{"plato": self.e.pollo.pk}]), "mesa_id": self.mesa.pk,
        })

        self.assertEqual((respuesta.status_code, respuesta.json()["code"]), (409, "mesa_invalida"))
        self.assertFalse(Pedido.objects.exists())

    def test_sin_menu_tambien_se_escanea_la_mesa_y_queda_en_el_consumo(self):
        self.e.menu.publicado = False
        self.e.menu.save()

        self.assertEqual(self.escanear(self.mesa.token).json()["status"], "mesa")
        datos = self.escanear(str(self.e.trabajador.token_qr), mesa_id=self.mesa.pk).json()

        self.assertEqual((datos["status"], datos["table"]), ("registered", "Mesa 3"))
        self.assertEqual(Consumo.objects.get().mesa, self.mesa)
        self.assertFalse(Pedido.objects.exists())

    def test_pantalla_pide_la_mesa_con_y_sin_menu(self):
        for publicado in (True, False):
            self.e.menu.publicado = publicado
            self.e.menu.save()
            pantalla = self.client.get(reverse("consumos:escaner"))
            self.assertContains(pantalla, "Escanea la mesa")
            self.assertNotContains(pantalla, "btn-despacho")
            self.assertNotContains(pantalla, "no tiene mesas activas")

    def test_aviso_si_el_local_no_tiene_mesas_activas(self):
        from mesas.models import Mesa

        Mesa.objects.filter(local=self.e.local).update(activa=False)
        self.assertContains(self.client.get(reverse("consumos:escaner")), "no tiene mesas activas")



class HistorialConPedidoTests(TestCase):
    def setUp(self):
        from mesas.models import Mesa

        self.e = crear_escenario()
        self.mesa = Mesa.objects.create(local=self.e.local, nombre="Mesa 3")

    def test_historial_muestra_folio_y_mesa(self):
        registrar_pedido(self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}], mesa_id=self.mesa.pk)
        registrar_pedido(self.e.otro.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}])

        for usuario in (self.e.admin, self.e.garzon_a):  # el garzón ve el día en curso
            self.client.force_login(usuario)
            historial = self.client.get(reverse("consumos:historial"))
            self.assertContains(historial, "0001</span> · Mesa 3")
            self.assertContains(historial, "0002</span> · Mesa 1")

    def test_consumo_sin_pedido_muestra_guion(self):
        from consumos.services import registrar_consumo_diario

        self.e.menu.publicado = False
        self.e.menu.save()
        registrar_consumo_diario(self.e.trabajador.pk, self.e.garzon_a)
        self.client.force_login(self.e.admin)

        historial = self.client.get(reverse("consumos:historial"))
        self.assertContains(historial, '<span class="text-secondary">—</span>')


class EtiquetaYConfiguracionDespachoTests(TestCase):
    def setUp(self):
        self.e = crear_escenario(cupo=2)

    def test_token_de_etiqueta_unico_y_distinto_del_qr_del_trabajador(self):
        a = registrar_pedido(self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}]).pedido
        b = registrar_pedido(self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}]).pedido

        self.assertEqual(len(a.token_etiqueta), 43)
        self.assertNotEqual(a.token_etiqueta, b.token_etiqueta)
        self.assertNotIn(str(self.e.trabajador.token_qr), (a.token_etiqueta, b.token_etiqueta))
        self.assertFalse(a.es_despacho)

    def test_migracion_rellena_un_token_distinto_por_pedido(self):
        from importlib import import_module

        from django.apps import apps

        for _ in range(2):
            registrar_pedido(self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}])
        antes = set(Pedido.objects.values_list("token_etiqueta", flat=True))
        migracion = import_module("pedidos.migrations.0003_despacho_y_etiqueta")
        migracion.rellenar_tokens(apps, None)  # solo rellena los vacíos: no cambia los existentes

        self.assertEqual(set(Pedido.objects.values_list("token_etiqueta", flat=True)), antes)
        self.assertEqual(len(antes), 2)

    def test_configuracion_de_cierre_y_envase(self):
        import datetime

        self.assertEqual(self.e.local.hora_cierre_despacho, datetime.time(10, 0))
        empresa = self.e.trabajador.empresa
        self.assertIsNone(empresa.hora_cierre_despacho)
        self.assertEqual(empresa.tipo_envase, "individual")

        self.client.force_login(self.e.admin)
        self.client.post(reverse("empresas:editar", args=[empresa.pk]), {
            "rut": empresa.rut, "nombre": empresa.nombre, "direccion": empresa.direccion,
            "encargado_personal": empresa.encargado_personal, "almuerzos_diarios": 2,
            "hora_cierre_despacho": "09:30", "tipo_envase": "marmita", "activa": "on",
        })
        self.client.post(reverse("locales:editar", args=[self.e.local.pk]), {
            "nombre": self.e.local.nombre, "direccion": self.e.local.direccion,
            "hora_cierre_despacho": "11:15", "activo": "on",
        })
        empresa.refresh_from_db(); self.e.local.refresh_from_db()
        self.assertEqual((empresa.hora_cierre_despacho, empresa.tipo_envase), (datetime.time(9, 30), "marmita"))
        self.assertEqual(self.e.local.hora_cierre_despacho, datetime.time(11, 15))


class DespachoServicioTests(TestCase):
    """Lista nominal de despacho: solo administrador, antes del cierre, éxito parcial."""

    def setUp(self):
        from trabajadores.models import Trabajador

        self.e = crear_escenario()
        self.empresa = self.e.trabajador.empresa
        self.e.pollo.porciones = None  # sin límite: estas pruebas miden cupo y cierre
        self.e.pollo.save()
        for i in range(28):  # 30 trabajadores en la empresa (incluye los 2 del escenario)
            Trabajador.objects.create(nombre=f"T{i:02d}", apellido="Despacho", rut=_rut_valido(30000000 + i), empresa=self.empresa)
        self.hoy = timezone.localdate()

    def a_las(self, hora, minuto=0):
        import datetime

        momento = timezone.make_aware(datetime.datetime.combine(self.hoy, datetime.time(hora, minuto)))
        return patch("django.utils.timezone.now", return_value=momento)

    def filas(self, trabajadores=None):
        trabajadores = trabajadores or self.empresa.trabajadores.filter(eliminado_en__isnull=True)
        return [{"trabajador": t, "token": nuevo_token(), "seleccion": [{"plato": self.e.pollo.pk}]} for t in trabajadores]

    def test_lista_de_30_con_uno_sin_cupo_crea_29_e_informa_1(self):
        with self.a_las(8):
            registrar_pedido(self.e.otro.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}])  # ya almorzó
            resultado = despacho.confirmar_lista(self.e.admin, self.empresa, self.hoy, self.filas())

        self.assertEqual((len(resultado.creados), resultado.total_errores), (29, 1))
        trabajador, codigo, mensaje = resultado.errores[0]
        self.assertEqual((trabajador, codigo), (self.e.otro, "cupo_agotado"))
        self.assertIn("Cupo diario agotado", mensaje)
        pedidos = despacho.pedidos_de_despacho(self.empresa, self.e.local, self.hoy)
        self.assertEqual(pedidos.count(), 29)
        self.assertTrue(all(p.es_despacho and p.mesa is None for p in pedidos))
        self.assertEqual({p.mesa_nombre for p in pedidos}, {"Despacho · Constructora ABC"})
        self.assertEqual(sorted(p.folio for p in pedidos), list(range(2, 31)))  # el folio 1 fue el del local

    def test_operador_no_puede_crear_pedidos_de_despacho(self):
        from django.core.exceptions import PermissionDenied

        with self.a_las(8):
            with self.assertRaises(PermissionDenied):
                despacho.confirmar_lista(self.e.garzon_a, self.empresa, self.hoy, self.filas())
            with self.assertRaises(PedidoRechazado) as error:
                _registrar_pedido(self.e.trabajador.pk, self.e.garzon_a, nuevo_token(), [{"plato": self.e.pollo.pk}], despacho=True)
        self.assertEqual(error.exception.codigo, "despacho_no_permitido")
        self.assertFalse(Pedido.objects.exists())

    def test_despues_del_cierre_no_se_agrega_ni_cambia_solo_se_anula(self):
        with self.a_las(9, 59):
            resultado = despacho.confirmar_lista(self.e.admin, self.empresa, self.hoy, self.filas([self.e.trabajador]))
        pedido = resultado.creados[0]

        with self.a_las(10):
            with self.assertRaises(despacho.ErrorDespacho) as error:
                despacho.confirmar_lista(self.e.admin, self.empresa, self.hoy, self.filas([self.e.otro]))
            self.assertEqual(error.exception.codigo, "lista_cerrada")
            with self.assertRaises(PedidoRechazado) as directo:
                _registrar_pedido(self.e.otro.pk, self.e.admin, nuevo_token(), [{"plato": self.e.pollo.pk}], despacho=True)
            self.assertEqual(directo.exception.codigo, "lista_cerrada")
            with self.assertRaises(PedidoRechazado) as cambio:
                cambiar_plato(pedido.items.get().pk, self.e.chuleta.pk, self.e.arroz.pk, self.e.admin)
            self.assertEqual(cambio.exception.codigo, "lista_cerrada")
            anular_consumo(pedido.consumo_id, self.e.admin, "El trabajador avisó tarde que no venía")
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Pedido.ANULADO)

    def test_la_excepcion_de_la_empresa_manda_sobre_el_local(self):
        import datetime

        self.empresa.hora_cierre_despacho = datetime.time(9, 0)
        self.empresa.save()
        with self.a_las(9, 30), self.assertRaises(despacho.ErrorDespacho):
            despacho.confirmar_lista(self.e.admin, self.empresa, self.hoy, self.filas([self.e.trabajador]))

        self.empresa.hora_cierre_despacho = datetime.time(11, 0)
        self.empresa.save()
        with self.a_las(10, 30):  # el local ya cerró (10:00), pero esta empresa cierra a las 11:00
            resultado = despacho.confirmar_lista(self.e.admin, self.empresa, self.hoy, self.filas([self.e.trabajador]))
        self.assertEqual(len(resultado.creados), 1)

    def test_antes_del_cierre_se_cambia_plato_y_se_quita_trabajador(self):
        with self.a_las(8):
            resultado = despacho.confirmar_lista(
                self.e.admin, self.empresa, self.hoy, self.filas([self.e.trabajador, self.e.otro])
            )
            uno, otro = resultado.creados
            cambiar_plato(uno.items.get().pk, self.e.chuleta.pk, self.e.arroz.pk, self.e.admin)
            quitado = despacho.confirmar_lista(self.e.admin, self.empresa, self.hoy, [], quitar=[otro])

        uno.refresh_from_db(); otro.refresh_from_db()
        self.assertEqual(str(uno.items.get()), "Chuleta de cerdo + Arroz")
        self.assertEqual(len(quitado.quitados), 1)
        self.assertEqual((otro.estado, otro.consumo.motivo_anulacion), (Pedido.ANULADO, despacho.MOTIVO_QUITADO))
        self.assertEqual(despacho.pedidos_de_despacho(self.empresa, self.e.local, self.hoy).count(), 1)

    def test_reintento_de_la_misma_lista_no_duplica(self):
        filas = self.filas([self.e.trabajador])
        with self.a_las(8):
            despacho.confirmar_lista(self.e.admin, self.empresa, self.hoy, filas)
            segundo = despacho.confirmar_lista(self.e.admin, self.empresa, self.hoy, filas)
        self.assertEqual((len(segundo.creados), len(segundo.sin_cambios)), (0, 1))
        self.assertEqual(Pedido.objects.count(), 1)

    def test_totales_por_plato(self):
        with self.a_las(8):
            filas = self.filas([self.e.trabajador, self.e.otro])
            filas[1]["seleccion"] = [chuleta_con(self.e, self.e.arroz)]
            despacho.confirmar_lista(self.e.admin, self.empresa, self.hoy, filas)
        pedidos = despacho.pedidos_de_despacho(self.empresa, self.e.local, self.hoy)
        self.assertEqual(despacho.totales_por_plato(pedidos), [("Chuleta de cerdo + Arroz", 1), ("Pollo asado", 1)])


def _rut_valido(cuerpo):
    suma, factor = 0, 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return f"{cuerpo}-{'0' if resto == 11 else 'K' if resto == 10 else resto}"
