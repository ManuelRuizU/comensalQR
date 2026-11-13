import threading
import unittest
from datetime import timedelta

from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from consumos.models import Consumo
from consumos.services import PedidoRechazado, anular_consumo, registrar_pedido
from menus import services as menu
from menus.escenario_prueba import crear_escenario, nuevo_token
from menus.models import MovimientoPorcion, ReservaPorcion

from .models import FolioDiario, Pedido
from .services import cambiar_plato


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
        self.assertEqual((pedido.folio, pedido.estado, pedido.mesa_nombre), (1, "pendiente", "Sin mesa"))
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
