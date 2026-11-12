from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from locales.models import Local

from .access_control import (
    MAX_INTENTOS_POR_CUENTA,
    MAX_INTENTOS_POR_CUENTA_IP,
    MENSAJE_LOGIN_INVALIDO,
    VENTANA,
    _obtener_bloqueado,
)
from .forms import OperadorForm
from .models import Administrador, IntentoAcceso, Operador


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

    def test_bloqueo_vigente_no_se_levanta_al_vencer_la_ventana(self):
        ahora = timezone.now()
        bloqueado_hasta = ahora + timedelta(minutes=5)
        IntentoAcceso.objects.create(
            clave="cuenta-bloqueada",
            intentos=MAX_INTENTOS_POR_CUENTA,
            ventana_desde=ahora - VENTANA - timedelta(minutes=1),
            bloqueado_hasta=bloqueado_hasta,
        )

        intento = _obtener_bloqueado("cuenta-bloqueada", ahora)

        self.assertEqual(intento.bloqueado_hasta, bloqueado_hasta)
        self.assertEqual(intento.intentos, MAX_INTENTOS_POR_CUENTA)

    def test_ventana_vencida_sin_bloqueo_se_reinicia(self):
        ahora = timezone.now()
        IntentoAcceso.objects.create(
            clave="cuenta-libre",
            intentos=3,
            ventana_desde=ahora - VENTANA - timedelta(minutes=1),
            bloqueado_hasta=ahora - timedelta(minutes=1),
        )

        intento = _obtener_bloqueado("cuenta-libre", ahora)

        self.assertEqual(intento.intentos, 0)
        self.assertIsNone(intento.bloqueado_hasta)


class CreacionOperadorTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="admin-password"
        )
        self.local = Local.objects.create(nombre="Casino Norte", direccion="Calle 1")
        self.client.force_login(self.admin)

    def test_reenvio_del_post_no_crea_otro_operador(self):
        url = reverse("operadores:crear")
        form_response = self.client.get(url)
        solicitud_id = form_response.context["form"]["solicitud_id"].value()
        datos = {
            "solicitud_id": solicitud_id,
            "nombre": "Ana",
            "apellido": "Rojas",
            "local": self.local.pk,
            "clave": "12345678",
        }

        primera_respuesta = self.client.post(url, datos)
        segunda_respuesta = self.client.post(url, datos)

        self.assertEqual(primera_respuesta.status_code, 200)
        self.assertIn("no-store", primera_respuesta["Cache-Control"])
        self.assertRedirects(segunda_respuesta, reverse("operadores:lista"))
        self.assertEqual(Operador.objects.count(), 1)
        self.assertEqual(Operador.objects.get().local, self.local)

    def test_operador_requiere_local(self):
        datos = {"solicitud_id": "solicitud", "nombre": "Ana", "apellido": "Rojas", "clave": "12345678"}
        form = OperadorForm(data=datos)
        self.assertFalse(form.is_valid())
        self.assertIn("local", form.errors)

        self.local.activo = False
        self.local.save(update_fields=["activo"])
        self.assertFalse(OperadorForm(data={**datos, "local": self.local.pk}).is_valid())

    def test_clave_de_operador_debe_tener_ocho_digitos(self):
        datos = {"solicitud_id": "solicitud", "nombre": "Ana", "apellido": "Rojas", "local": self.local.pk}

        self.assertFalse(OperadorForm(data={**datos, "clave": "1234"}).is_valid())
        self.assertFalse(OperadorForm(data={**datos, "clave": "123456"}).is_valid())
        self.assertFalse(OperadorForm(data={**datos, "clave": "１２３４５６７８"}).is_valid())
        self.assertTrue(OperadorForm(data={**datos, "clave": "12345678"}).is_valid())


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
        self.local = Local.objects.create(nombre="Casino Norte", direccion="Calle 1")
        self.operador = Operador.objects.create(usuario=self.usuario, local=self.local)

    def test_desactivar_operador_corta_su_acceso(self):
        mozo = Client()
        mozo.force_login(self.usuario)
        self.assertEqual(mozo.get(reverse("consumos:escaner")).status_code, 200)

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operadores:editar", args=[self.operador.pk]), {"local": self.local.pk}
        )

        self.assertRedirects(response, reverse("operadores:lista"))
        self.operador.refresh_from_db()
        self.assertFalse(self.operador.activo)
        self.assertEqual(mozo.get(reverse("consumos:escaner")).status_code, 302)

    def test_cambiar_clave(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operadores:editar", args=[self.operador.pk]),
            {"activo": "on", "local": self.local.pk, "nueva_clave": "87654321"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "87654321")
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("87654321"))

    def test_clave_de_6_digitos_es_rechazada(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operadores:editar", args=[self.operador.pk]),
            {"activo": "on", "local": self.local.pk, "nueva_clave": "654321"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("nueva_clave", response.context["form"].errors)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("123456"))

    def test_cambiar_local_y_conservar_uno_desactivado(self):
        otro = Local.objects.create(nombre="Casino Sur", direccion="Calle 2")
        self.local.activo = False
        self.local.save(update_fields=["activo"])
        self.client.force_login(self.admin)
        url = reverse("operadores:editar", args=[self.operador.pk])

        # Puede seguir en su local aunque se haya desactivado...
        self.assertRedirects(self.client.post(url, {"activo": "on", "local": self.local.pk}), reverse("operadores:lista"))
        # ...y cambiarse a otro activo.
        self.assertRedirects(self.client.post(url, {"activo": "on", "local": otro.pk}), reverse("operadores:lista"))
        self.operador.refresh_from_db()
        self.assertEqual(self.operador.local, otro)

    def test_operador_no_puede_editar_operadores(self):
        self.client.force_login(self.usuario)
        response = self.client.post(reverse("operadores:editar", args=[self.operador.pk]), {})
        self.assertEqual(response.status_code, 302)
        self.operador.refresh_from_db()
        self.assertTrue(self.operador.activo)


CLAVE_ADMIN = "Almuerzo-Seguro-2026"


class RegistroInicialTests(TestCase):
    def datos(self, **cambios):
        datos = {
            "local-nombre": "Restaurante El Comensal",
            "local-direccion": "Av. Central 100",
            "local-telefono": "",
            "admin-nombre": "Marta",
            "admin-apellido": "Lagos",
            "admin-correo": "Marta.Lagos@Ejemplo.cl",
            "admin-clave": CLAVE_ADMIN,
            "admin-clave_confirmacion": CLAVE_ADMIN,
        }
        datos.update(cambios)
        return datos

    def test_sin_administradores_el_login_lleva_al_registro(self):
        self.assertRedirects(self.client.get(reverse("login")), reverse("registro_inicial"))

    def test_registro_crea_local_y_administrador_y_entra(self):
        response = self.client.post(reverse("registro_inicial"), self.datos())

        self.assertRedirects(response, reverse("consumos:dashboard"))
        local = Local.objects.get()
        usuario = get_user_model().objects.get()
        self.assertEqual(local.nombre, "Restaurante El Comensal")
        self.assertTrue(local.activo)
        self.assertEqual((usuario.username, usuario.email), ("marta.lagos@ejemplo.cl", "marta.lagos@ejemplo.cl"))
        self.assertTrue(usuario.is_staff)
        self.assertEqual(usuario.perfil_administrador.local, local)
        self.assertEqual(response.wsgi_request.user, usuario)

    def test_registro_no_disponible_si_ya_hay_administrador(self):
        get_user_model().objects.create_user(username="admin", password="x", is_staff=True)

        self.assertRedirects(self.client.get(reverse("registro_inicial")), reverse("login"))
        self.client.post(reverse("registro_inicial"), self.datos())
        self.assertFalse(Local.objects.exists())
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_rechaza_clave_debil_o_distinta(self):
        debil = self.client.post(
            reverse("registro_inicial"),
            self.datos(**{"admin-clave": "12345678", "admin-clave_confirmacion": "12345678"}),
        )
        distinta = self.client.post(
            reverse("registro_inicial"), self.datos(**{"admin-clave_confirmacion": "Otra-Clave-2026"})
        )

        self.assertIn("clave", debil.context["form_admin"].errors)
        self.assertIn("clave_confirmacion", distinta.context["form_admin"].errors)
        self.assertFalse(Local.objects.exists())

    def test_administrador_ingresa_con_su_correo_sin_importar_mayusculas(self):
        self.client.post(reverse("registro_inicial"), self.datos())
        self.client.logout()

        response = self.client.post(
            reverse("login"), {"username": " MARTA.lagos@ejemplo.cl ", "password": CLAVE_ADMIN}
        )

        self.assertRedirects(response, reverse("consumos:dashboard"))


class AdministradoresTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.local = Local.objects.create(nombre="Casino Norte", direccion="Calle 1")
        self.admin = User.objects.create_user(
            username="admin@ejemplo.cl", email="admin@ejemplo.cl", password="x", is_staff=True
        )
        Administrador.objects.create(usuario=self.admin, local=self.local)
        self.client.force_login(self.admin)

    def crear(self, **cambios):
        datos = {
            "nombre": "Pablo",
            "apellido": "Mena",
            "correo": "pablo@ejemplo.cl",
            "local": self.local.pk,
            "clave": CLAVE_ADMIN,
            "clave_confirmacion": CLAVE_ADMIN,
        }
        datos.update(cambios)
        return self.client.post(reverse("administradores:crear"), datos)

    def test_crear_administrador_con_local(self):
        self.assertRedirects(self.crear(), reverse("administradores:lista"))

        nuevo = get_user_model().objects.get(username="pablo@ejemplo.cl")
        self.assertTrue(nuevo.is_staff)
        self.assertEqual(nuevo.perfil_administrador.local, self.local)
        self.assertTrue(nuevo.check_password(CLAVE_ADMIN))

    def test_correo_repetido_es_rechazado(self):
        response = self.crear(correo="ADMIN@ejemplo.cl")

        self.assertIn("correo", response.context["form"].errors)

    def test_no_puede_desactivarse_a_si_mismo(self):
        url = reverse("administradores:editar", args=[self.admin.pk])

        response = self.client.post(url, {"local": self.local.pk})

        self.assertIn("activo", response.context["form"].errors)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_desactivar_otro_administrador_le_quita_el_acceso(self):
        self.crear()
        otro = get_user_model().objects.get(username="pablo@ejemplo.cl")
        sesion_otro = Client()
        sesion_otro.force_login(otro)

        response = self.client.post(reverse("administradores:editar", args=[otro.pk]), {"local": self.local.pk})

        self.assertRedirects(response, reverse("administradores:lista"))
        otro.refresh_from_db()
        self.assertFalse(otro.is_active)
        self.assertEqual(sesion_otro.get(reverse("consumos:dashboard")).status_code, 302)

    def test_asignar_local_a_administrador_antiguo_sin_perfil(self):
        antiguo = get_user_model().objects.create_superuser(username="root", email="", password="x")

        self.client.post(
            reverse("administradores:editar", args=[antiguo.pk]), {"local": self.local.pk, "activo": "on"}
        )

        self.assertEqual(Administrador.objects.get(usuario=antiguo).local, self.local)

    def test_cambiar_propia_clave_mantiene_la_sesion(self):
        url = reverse("administradores:editar", args=[self.admin.pk])

        self.client.post(url, {
            "local": self.local.pk, "activo": "on",
            "nueva_clave": CLAVE_ADMIN, "nueva_clave_confirmacion": CLAVE_ADMIN,
        })

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(CLAVE_ADMIN))
        self.assertEqual(self.client.get(reverse("consumos:dashboard")).status_code, 200)

    def test_operador_no_accede_a_administradores(self):
        mozo = get_user_model().objects.create_user(username="mozo", password="x")
        Operador.objects.create(usuario=mozo, local=self.local)
        self.client.force_login(mozo)

        self.assertEqual(self.client.get(reverse("administradores:lista")).status_code, 302)
        self.assertEqual(self.crear().status_code, 302)
        self.assertFalse(get_user_model().objects.filter(username="pablo@ejemplo.cl").exists())
