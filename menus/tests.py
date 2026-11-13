from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .escenario_prueba import crear_escenario
from .models import MenuDia, MovimientoPorcion, PlatoDia, TiempoMenu


class TiemposInicialesTests(TestCase):
    def test_migracion_crea_los_cuatro_tiempos_con_solo_fondo_obligatorio(self):
        tiempos = list(TiempoMenu.objects.values_list("nombre", "obligatorio"))
        self.assertEqual(tiempos, [("Fondo", True), ("Ensalada", False), ("Postre", False), ("Bebida", False)])


class AdministracionMenuTests(TestCase):
    def setUp(self):
        self.e = crear_escenario(publicado=False)
        self.client.force_login(self.e.admin)
        self.accion = reverse("menus:accion", args=[self.e.menu.pk])
        self.fondo = TiempoMenu.objects.get(nombre="Fondo")

    def test_pantalla_del_menu_muestra_platos_y_porciones(self):
        response = self.client.get(reverse("menus:menu_dia"))
        self.assertContains(response, "Chuleta de cerdo")
        self.assertContains(response, "Borrador")

    def test_agregar_plato_registra_la_carga(self):
        self.client.post(self.accion, {"accion": "agregar_plato", "tiempo": self.fondo.pk, "nombre": "Cazuela", "porciones": 20})

        plato = PlatoDia.objects.get(nombre="Cazuela")
        self.assertEqual(plato.porciones, 20)
        self.assertEqual(MovimientoPorcion.objects.get(plato=plato).cantidad, 20)

    def test_publicar_exige_platos_en_tiempos_obligatorios(self):
        PlatoDia.objects.filter(tiempo=self.fondo).update(tiempo=TiempoMenu.objects.get(nombre="Postre"))
        self.client.post(self.accion, {"accion": "publicar"})
        self.e.menu.refresh_from_db()
        self.assertFalse(self.e.menu.publicado)

        PlatoDia.objects.filter(nombre="Pollo asado").update(tiempo=self.fondo)
        self.client.post(self.accion, {"accion": "publicar"})
        self.e.menu.refresh_from_db()
        self.assertTrue(self.e.menu.publicado)

    def test_ajuste_con_motivo_y_agotado(self):
        self.e.menu.publicado = True
        self.e.menu.save()
        datos = {"accion": "ajustar", "tipo": "plato", "item": self.e.pollo.pk, "porciones": 15}

        self.client.post(self.accion, datos)  # sin motivo: rechazado
        self.e.pollo.refresh_from_db()
        self.assertEqual(self.e.pollo.porciones, 10)

        self.client.post(self.accion, {**datos, "motivo": "Llegaron más pollos"})
        self.client.post(self.accion, {"accion": "agotar", "tipo": "acompanamiento", "item": self.e.pure.pk})
        self.e.pollo.refresh_from_db(); self.e.pure.refresh_from_db()
        self.assertEqual(self.e.pollo.porciones, 15)
        self.assertTrue(self.e.pure.agotado)
        movimiento = MovimientoPorcion.objects.get(tipo="ajuste")
        self.assertEqual((movimiento.cantidad, movimiento.motivo), (5, "Llegaron más pollos"))

    def test_copiar_de_otro_dia_sin_publicar(self):
        manana = timezone.localdate() + timedelta(days=1)
        self.client.post(reverse("menus:crear"), {"local": self.e.local.pk, "fecha": manana.isoformat(), "origen": self.e.menu.pk})

        copia = MenuDia.objects.get(fecha=manana)
        self.assertFalse(copia.publicado)
        self.assertEqual(
            sorted(copia.platos.values_list("nombre", "porciones")),
            sorted(self.e.menu.platos.values_list("nombre", "porciones")),
        )
        self.assertEqual(copia.platos.get(nombre="Chuleta de cerdo").acompanamientos.count(), 2)

    def test_eliminar_plato_sin_ventas(self):
        self.client.post(self.accion, {"accion": "eliminar", "tipo": "plato", "item": self.e.pollo.pk})
        self.assertFalse(PlatoDia.objects.filter(pk=self.e.pollo.pk).exists())

    def test_disponibilidad_con_etag_responde_304_si_nada_cambio(self):
        url = reverse("menus:disponibilidad", args=[self.e.menu.pk])
        primera = self.client.get(url)
        segunda = self.client.get(url, HTTP_IF_NONE_MATCH=primera["ETag"])
        self.e.pollo.vendidas = 1
        self.e.pollo.save()
        tercera = self.client.get(url, HTTP_IF_NONE_MATCH=primera["ETag"])

        self.assertEqual((primera.status_code, segunda.status_code, tercera.status_code), (200, 304, 200))

    def test_informe_de_cierre_y_tiempos(self):
        self.assertContains(self.client.get(reverse("menus:cierre", args=[self.e.menu.pk])), "Chuleta de cerdo")
        self.client.post(reverse("menus:tiempos") + f"?editar={self.fondo.pk}", {"nombre": "Fondo", "orden": 1, "activo": "on"})
        self.fondo.refresh_from_db()
        self.assertFalse(self.fondo.obligatorio)

    def test_garzon_no_administra_el_menu(self):
        self.client.force_login(self.e.garzon_a)
        self.assertEqual(self.client.get(reverse("menus:menu_dia")).status_code, 302)
        self.client.post(self.accion, {"accion": "publicar"})
        self.e.menu.refresh_from_db()
        self.assertFalse(self.e.menu.publicado)
