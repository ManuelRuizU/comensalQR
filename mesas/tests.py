import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from locales.models import Local

from .models import Mesa


class MesaModeloTests(TestCase):
    def setUp(self):
        self.local = Local.objects.create(nombre="Restaurante de Prueba", direccion="Calle 1")

    def test_token_aleatorio_de_43_caracteres_que_no_parece_uuid(self):
        mesa = Mesa.objects.create(local=self.local, nombre="Mesa 1")
        otra = Mesa.objects.create(local=self.local, nombre="Mesa 2")

        self.assertEqual(len(mesa.token), 43)
        self.assertNotEqual(mesa.token, otra.token)
        with self.assertRaises(ValueError):
            uuid.UUID(mesa.token)

    def test_nombre_unico_por_local(self):
        Mesa.objects.create(local=self.local, nombre="Mesa 1")
        otro_local = Local.objects.create(nombre="Otro local", direccion="Calle 2")
        Mesa.objects.create(local=otro_local, nombre="Mesa 1")  # en otro local, sí

        with self.assertRaises(IntegrityError), transaction.atomic():
            Mesa.objects.create(local=self.local, nombre="Mesa 1")


class AdministracionMesasTests(TestCase):
    def setUp(self):
        from menus.escenario_prueba import crear_escenario

        self.e = crear_escenario()
        self.client.force_login(self.e.admin)

    def test_crear_desactivar_y_reactivar(self):
        self.client.post(reverse("mesas:crear"), {"local": self.e.local.pk, "nombre": "Mesa 3"})
        mesa = Mesa.objects.get(nombre="Mesa 3")
        self.assertTrue(mesa.activa)

        self.client.post(reverse("mesas:estado", args=[mesa.pk]), {"accion": "desactivar"})
        mesa.refresh_from_db()
        self.assertFalse(mesa.activa)
        self.client.post(reverse("mesas:estado", args=[mesa.pk]), {"accion": "reactivar"})
        mesa.refresh_from_db()
        self.assertTrue(mesa.activa)

    def test_nombre_repetido_muestra_error(self):
        self.client.post(reverse("mesas:crear"), {"local": self.e.local.pk, "nombre": "Mesa 3"})
        respuesta = self.client.post(reverse("mesas:crear"), {"local": self.e.local.pk, "nombre": "Mesa 3"}, follow=True)

        self.assertContains(respuesta, "Ya existe «Mesa 3»")
        self.assertEqual(Mesa.objects.count(), 1)

    def test_pdf_con_los_qr_de_las_mesas_activas(self):
        Mesa.objects.create(local=self.e.local, nombre="Mesa 1")
        Mesa.objects.create(local=self.e.local, nombre="Mesa 2", activa=False)

        respuesta = self.client.get(reverse("mesas:pdf"), {"local": self.e.local.pk})

        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertTrue(respuesta.content.startswith(b"%PDF"))
        self.assertIn(b"/Count 1", respuesta.content)  # una hoja: solo la mesa activa

    def test_el_qr_de_la_tarjeta_contiene_solo_el_token(self):
        from unittest.mock import patch

        from . import tarjetas

        mesa = Mesa.objects.create(local=self.e.local, nombre="Mesa 1")
        with patch.object(tarjetas, "imagen_qr", wraps=tarjetas.imagen_qr) as qr:
            tarjeta = tarjetas.tarjeta_mesa(mesa)

        self.assertEqual(tarjeta.size, (1000, 1220))
        self.assertEqual(qr.call_args.args[0], mesa.token)

    def test_garzon_no_administra_mesas(self):
        self.client.force_login(self.e.garzon_a)
        self.assertEqual(self.client.get(reverse("mesas:lista")).status_code, 302)
        self.client.post(reverse("mesas:crear"), {"local": self.e.local.pk, "nombre": "Mesa 9"})
        self.assertFalse(Mesa.objects.exists())

    def test_pantalla_lista_las_mesas(self):
        Mesa.objects.create(local=self.e.local, nombre="Terraza 1")
        self.assertContains(self.client.get(reverse("mesas:lista")), "Terraza 1")
