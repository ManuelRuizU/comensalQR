from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .access_control import (
    MAX_INTENTOS_POR_CUENTA,
    MAX_INTENTOS_POR_CUENTA_IP,
    MENSAJE_LOGIN_INVALIDO,
)
from .forms import OperadorForm
from .models import IntentoAcceso, Operador


class AccesoOperadorTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador", password="1234"
        )
        self.operador = Operador.objects.create(usuario=self.usuario, activo=False)

    def test_operador_inactivo_no_entra_en_bucle_de_redireccion(self):
        response = self.client.post(
            reverse("login"), {"username": "operador", "password": "1234"}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MENSAJE_LOGIN_INVALIDO)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_usuario_sin_perfil_operador_no_entra_en_bucle(self):
        self.operador.delete()

        response = self.client.post(
            reverse("login"), {"username": "operador", "password": "1234"}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MENSAJE_LOGIN_INVALIDO)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_cuenta_no_disponible_y_clave_incorrecta_muestran_mismo_mensaje(self):
        correcta = self.client.post(
            reverse("login"), {"username": "operador", "password": "1234"}
        )
        incorrecta = self.client.post(
            reverse("login"), {"username": "operador", "password": "otra-clave"}
        )

        self.assertContains(correcta, MENSAJE_LOGIN_INVALIDO)
        self.assertContains(incorrecta, MENSAJE_LOGIN_INVALIDO)
        self.assertFalse(correcta.wsgi_request.user.is_authenticated)
        self.assertFalse(incorrecta.wsgi_request.user.is_authenticated)

    def test_limita_intentos_fallidos_por_cuenta_y_direccion(self):
        for _ in range(MAX_INTENTOS_POR_CUENTA_IP):
            response = self.client.post(
                reverse("login"), {"username": "operador", "password": "incorrecta"}
            )
            self.assertContains(response, MENSAJE_LOGIN_INVALIDO)

        response = self.client.post(
            reverse("login"), {"username": "operador", "password": "1234"}
        )

        self.assertContains(response, MENSAJE_LOGIN_INVALIDO)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertTrue(IntentoAcceso.objects.filter(bloqueado_hasta__isnull=False).exists())

    @override_settings(
        LOGIN_RATE_LIMIT_IP_HEADER="HTTP_X_REAL_IP",
        LOGIN_RATE_LIMIT_TRUSTED_PROXY_IPS=("10.0.0.10",),
    )
    def test_usa_ip_del_proxy_configurado_en_lugar_de_la_ip_compartida(self):
        for numero in range(6):
            self.client.post(
                reverse("login"),
                {"username": "operador", "password": "incorrecta"},
                REMOTE_ADDR="10.0.0.10",
                HTTP_X_REAL_IP=f"198.51.100.{numero + 1}",
            )

        self.assertFalse(IntentoAcceso.objects.filter(bloqueado_hasta__isnull=False).exists())

    @override_settings(
        LOGIN_RATE_LIMIT_IP_HEADER="HTTP_X_REAL_IP",
        LOGIN_RATE_LIMIT_TRUSTED_PROXY_IPS=("10.0.0.10",),
    )
    def test_limita_intentos_globales_de_cuenta_entre_distintas_ips(self):
        self.operador.activo = True
        self.operador.save(update_fields=["activo"])
        self.usuario.set_password("1234")
        self.usuario.save(update_fields=["password"])

        for numero in range(MAX_INTENTOS_POR_CUENTA):
            self.client.post(
                reverse("login"),
                {"username": "operador", "password": "incorrecta"},
                REMOTE_ADDR="10.0.0.10",
                HTTP_X_REAL_IP=f"198.51.100.{numero + 1}",
            )

        response = self.client.post(
            reverse("login"),
            {"username": "operador", "password": "1234"},
            REMOTE_ADDR="10.0.0.10",
            HTTP_X_REAL_IP="203.0.113.1",
        )

        self.assertContains(response, MENSAJE_LOGIN_INVALIDO)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    @override_settings(
        LOGIN_RATE_LIMIT_IP_HEADER="HTTP_X_REAL_IP",
        LOGIN_RATE_LIMIT_TRUSTED_PROXY_IPS=("10.0.0.10",),
    )
    def test_no_confia_en_el_encabezado_si_la_conexion_no_viene_del_proxy(self):
        for numero in range(MAX_INTENTOS_POR_CUENTA_IP + 1):
            self.client.post(
                reverse("login"),
                {"username": "operador", "password": "incorrecta"},
                REMOTE_ADDR="192.0.2.10",
                HTTP_X_REAL_IP=f"198.51.100.{numero + 1}",
            )

        self.assertTrue(IntentoAcceso.objects.filter(bloqueado_hasta__isnull=False).exists())


class CreacionOperadorTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="admin-password"
        )
        self.client.force_login(self.admin)

    def test_reenvio_del_post_no_crea_otro_operador(self):
        url = reverse("operadores:crear")
        form_response = self.client.get(url)
        solicitud_id = form_response.context["form"]["solicitud_id"].value()
        datos = {
            "solicitud_id": solicitud_id,
            "nombre": "Ana",
            "apellido": "Rojas",
            "clave": "123456",
        }

        primera_respuesta = self.client.post(url, datos)
        segunda_respuesta = self.client.post(url, datos)

        self.assertEqual(primera_respuesta.status_code, 200)
        self.assertIn("no-store", primera_respuesta["Cache-Control"])
        self.assertRedirects(segunda_respuesta, reverse("operadores:lista"))
        self.assertEqual(Operador.objects.count(), 1)

    def test_clave_de_operador_debe_tener_seis_digitos(self):
        datos = {"solicitud_id": "solicitud", "nombre": "Ana", "apellido": "Rojas"}

        self.assertFalse(OperadorForm(data={**datos, "clave": "1234"}).is_valid())
        self.assertFalse(OperadorForm(data={**datos, "clave": "１２３４５６"}).is_valid())
        self.assertTrue(OperadorForm(data={**datos, "clave": "123456"}).is_valid())


class AdminLoginRoutingTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="AdminPass123!"
        )

    def test_admin_login_redirige_al_login_con_proteccion_de_intentos(self):
        response = self.client.get("/admin/login/?next=/admin/")

        self.assertRedirects(response, "/accounts/login/?next=/admin/")
        login_page = self.client.get(response.url)
        self.assertContains(login_page, 'name="next" value="/admin/"')

        response = self.client.post(
            reverse("login"),
            {"username": "admin", "password": "AdminPass123!", "next": "/admin/"},
        )

        self.assertRedirects(response, "/admin/")
        self.assertEqual(response.wsgi_request.user, self.admin)

    def test_no_se_publican_rutas_de_recuperacion_de_clave_sin_configuracion(self):
        response = self.client.get("/accounts/password_reset/")

        self.assertEqual(response.status_code, 404)


class EditarOperadorTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username="admin", password="x", is_staff=True)
        self.usuario = User.objects.create_user(username="mozo.uno", password="123456")
        self.operador = Operador.objects.create(usuario=self.usuario)

    def test_desactivar_operador_corta_su_acceso(self):
        mozo = Client()
        mozo.force_login(self.usuario)
        self.assertEqual(mozo.get(reverse("consumos:escaner")).status_code, 200)

        self.client.force_login(self.admin)
        response = self.client.post(reverse("operadores:editar", args=[self.operador.pk]), {})

        self.assertRedirects(response, reverse("operadores:lista"))
        self.operador.refresh_from_db()
        self.assertFalse(self.operador.activo)
        self.assertEqual(mozo.get(reverse("consumos:escaner")).status_code, 302)

    def test_cambiar_clave(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operadores:editar", args=[self.operador.pk]),
            {"activo": "on", "nueva_clave": "654321"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "654321")
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("654321"))

    def test_clave_de_4_digitos_es_rechazada(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operadores:editar", args=[self.operador.pk]),
            {"activo": "on", "nueva_clave": "1234"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("nueva_clave", response.context["form"].errors)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("123456"))

    def test_operador_no_puede_editar_operadores(self):
        self.client.force_login(self.usuario)
        response = self.client.post(reverse("operadores:editar", args=[self.operador.pk]), {})
        self.assertEqual(response.status_code, 302)
        self.operador.refresh_from_db()
        self.assertTrue(self.operador.activo)
