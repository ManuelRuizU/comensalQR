import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase

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
