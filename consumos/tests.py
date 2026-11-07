from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from empresas.models import Empresa
from operadores.models import Operador
from trabajadores.models import Trabajador

from .models import Consumo


class ConsumoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador",
            password="una-clave-segura",
        )
        Operador.objects.create(usuario=self.usuario)
        self.empresa = Empresa.objects.create(nombre="Constructora ABC")
        self.trabajador = Trabajador.objects.create(
            nombre="Juan",
            apellido="Perez",
            rut="11111111-1",
            empresa=self.empresa,
        )

    def test_trabajador_recibe_token_qr(self):
        self.assertIsNotNone(self.trabajador.token_qr)

    def test_no_permite_dos_consumos_el_mismo_dia(self):
        Consumo.objects.create(
            trabajador=self.trabajador,
            fecha=date(2026, 9, 30),
            operador=self.usuario,
        )

        with self.assertRaises(IntegrityError):
            Consumo.objects.create(
                trabajador=self.trabajador,
                fecha=date(2026, 9, 30),
                operador=self.usuario,
            )

    def test_dashboard_requiere_autenticacion(self):
        response = self.client.get(reverse("consumos:dashboard"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('consumos:dashboard')}",
        )

    def test_historial_requiere_autenticacion(self):
        response = self.client.get(reverse("consumos:historial"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('consumos:historial')}",
        )

    def test_historial_filtra_por_fecha(self):
        self.client.force_login(self.usuario)
        Consumo.objects.create(
            trabajador=self.trabajador,
            fecha=date(2026, 9, 30),
            operador=self.usuario,
        )

        response = self.client.get(reverse("consumos:historial"), {"fecha": "2026-09-30"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.trabajador.nombre)
