from datetime import date
from importlib import import_module
from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from empresas.models import Empresa
from locales.models import Local
from operadores.models import Operador
from trabajadores.models import Trabajador

from .models import Consumo
from .services import ResultadoConsumo


class ConsumoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador",
            password="una-clave-segura",
        )
        Operador.objects.create(usuario=self.usuario)
        self.empresa = Empresa.objects.create(
            nombre="Constructora ABC",
            rut="76111111-6",
            direccion="Av. Principal 123",
            encargado_personal="Responsable de Personal",
        )
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
        # El filtro por fecha es del administrador; el operador solo ve el día en curso.
        self.client.force_login(
            get_user_model().objects.create_user(username="admin-historial", password="x", is_staff=True)
        )
        Consumo.objects.create(
            trabajador=self.trabajador,
            fecha=date(2026, 9, 30),
            operador=self.usuario,
        )

        response = self.client.get(reverse("consumos:historial"), {"fecha": "2026-09-30"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.trabajador.nombre)

    def test_hora_de_consumo_duplicado_usa_zona_horaria_local(self):
        self.client.force_login(self.usuario)
        consumo = Consumo.objects.create(
            trabajador=self.trabajador,
            fecha=timezone.localdate(),
            operador=self.usuario,
        )
        consumo.registrado_en = datetime(2026, 8, 1, 15, 7, tzinfo=datetime_timezone.utc)
        consumo.save(update_fields=["registrado_en"])

        with timezone.override("America/Santiago"):
            with patch(
                "consumos.views.registrar_consumo_diario",
                return_value=ResultadoConsumo(consumo, False, 1, 1),
            ):
                response = self.client.post(
                    reverse("consumos:escaner"),
                    {"token": str(self.trabajador.token_qr)},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )

        self.assertEqual(response.json()["time"], "11:07")

    def test_admin_no_puede_editar_ni_borrar_consumos_historicos(self):
        admin_user = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="admin-password"
        )
        request = RequestFactory().get("/admin/consumos/consumo/")
        request.user = admin_user
        consumo_admin = admin.site._registry[Consumo]

        self.assertEqual(
            set(consumo_admin.get_readonly_fields(request)),
            {"trabajador", "fecha", "numero", "operador", "local", "registrado_en", "metodo"},
        )
        self.assertFalse(consumo_admin.has_add_permission(request))
        self.assertFalse(consumo_admin.has_delete_permission(request))


class CupoDiarioPorEmpresaTests(TestCase):
    """Caso del cliente: RUT 12492336-0 trabaja en A (1 almuerzo) y en B (2 almuerzos)."""

    RUT = "12492336-0"

    def setUp(self):
        self.operador = get_user_model().objects.create_user(username="mozo", password="x")
        Operador.objects.create(usuario=self.operador)
        self.admin = get_user_model().objects.create_user(username="admin", password="x", is_staff=True)
        self.empresa_a = Empresa.objects.create(
            nombre="Empresa A", rut="76111111-6", direccion="Dir A", encargado_personal="RRHH A"
        )
        self.empresa_b = Empresa.objects.create(
            nombre="Empresa B", rut="76222222-1", direccion="Dir B",
            encargado_personal="RRHH B", almuerzos_diarios=2,
        )
        self.en_a = Trabajador.objects.create(
            nombre="Pedro", apellido="Soto", rut=self.RUT, empresa=self.empresa_a
        )
        self.en_b = Trabajador.objects.create(
            nombre="Pedro", apellido="Soto", rut="12.492.336-0", empresa=self.empresa_b
        )

    def escanear(self, trabajador):
        return self.client.post(
            reverse("consumos:escaner"),
            {"token": str(trabajador.token_qr)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        ).json()

    def test_mismo_rut_en_dos_empresas_tiene_qr_e_historial_independientes(self):
        self.assertNotEqual(self.en_a.token_qr, self.en_b.token_qr)
        self.assertEqual(self.en_b.rut, self.RUT)

    def test_cupos_independientes_por_empresa(self):
        self.client.force_login(self.operador)

        self.assertEqual(self.escanear(self.en_a)["status"], "registered")
        bloqueo_a = self.escanear(self.en_a)
        self.assertEqual(bloqueo_a["status"], "duplicate")
        self.assertEqual((bloqueo_a["used"], bloqueo_a["quota"]), (1, 1))

        primero_b = self.escanear(self.en_b)
        self.assertEqual(primero_b["message"], "Almuerzo 1 de 2 registrado.")
        self.assertEqual(self.escanear(self.en_b)["message"], "Almuerzo 2 de 2 registrado.")
        bloqueo_b = self.escanear(self.en_b)
        self.assertEqual(bloqueo_b["status"], "duplicate")
        self.assertEqual((bloqueo_b["used"], bloqueo_b["quota"]), (2, 2))

        hoy = timezone.localdate()
        self.assertEqual(Consumo.objects.filter(trabajador__rut=self.RUT, fecha=hoy).count(), 3)
        self.assertEqual(Consumo.objects.filter(trabajador=self.en_a).count(), 1)
        self.assertEqual(Consumo.objects.filter(trabajador=self.en_b).count(), 2)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("consumos:historial"), {"rut": "12.492.336-0"})
        self.assertEqual(response.context["consumos"].paginator.count, 3)
        response = self.client.get(
            reverse("consumos:historial"), {"rut": self.RUT, "empresa": self.empresa_b.pk}
        )
        self.assertEqual(response.context["consumos"].paginator.count, 2)

    def test_desvinculado_de_b_y_contratado_por_c(self):
        self.en_b.activo = False
        self.en_b.eliminado_en = timezone.now()
        self.en_b.save(update_fields=["activo", "eliminado_en"])
        empresa_c = Empresa.objects.create(
            nombre="Empresa C", rut="76333333-7", direccion="Dir C", encargado_personal="RRHH C"
        )
        en_c = Trabajador.objects.create(nombre="Pedro", apellido="Soto", rut=self.RUT, empresa=empresa_c)
        self.client.force_login(self.operador)

        respuesta_b = self.client.post(
            reverse("consumos:escaner"),
            {"token": str(self.en_b.token_qr)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(respuesta_b.status_code, 400)
        self.assertEqual(self.escanear(self.en_a)["status"], "registered")
        self.assertEqual(self.escanear(en_c)["status"], "registered")
        self.assertEqual(self.escanear(en_c)["status"], "duplicate")
        self.assertEqual(Consumo.objects.filter(trabajador__rut=self.RUT).count(), 2)

    def test_excepcion_individual_sobre_cupo_de_empresa(self):
        self.en_a.almuerzos_diarios = 3
        self.en_a.save(update_fields=["almuerzos_diarios"])
        self.client.force_login(self.operador)

        for _ in range(3):
            self.assertEqual(self.escanear(self.en_a)["status"], "registered")
        self.assertEqual(self.escanear(self.en_a)["status"], "duplicate")
        self.assertEqual(
            list(Consumo.objects.filter(trabajador=self.en_a).order_by("numero").values_list("numero", flat=True)),
            [1, 2, 3],
        )

    def test_hueco_en_la_numeracion_no_bloquea_el_cupo_restante(self):
        # Quedó solo el almuerzo n.º 2 del día (p. ej. se borró el n.º 1 desde la base).
        Consumo.objects.create(trabajador=self.en_b, fecha=timezone.localdate(), numero=2, operador=self.operador)
        self.client.force_login(self.operador)

        respuesta = self.escanear(self.en_b)

        self.assertEqual(respuesta["status"], "registered")
        self.assertEqual(respuesta["number"], 3)
        self.assertEqual(self.escanear(self.en_b)["status"], "duplicate")

    def test_historial_lista_trabajadores_solo_de_la_empresa_elegida(self):
        self.client.force_login(self.admin)

        sin_empresa = self.client.get(reverse("consumos:historial"))
        con_empresa = self.client.get(reverse("consumos:historial"), {"empresa": self.empresa_a.pk})

        self.assertEqual(list(sin_empresa.context["trabajadores"]), [])
        self.assertEqual(list(con_empresa.context["trabajadores"]), [self.en_a])

    def test_rut_duplicado_en_la_misma_empresa_muestra_error_y_no_500(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("trabajadores:crear"),
            {"empresa": self.empresa_a.pk, "nombre": "Otro", "apellido": "Nombre", "rut": "12.492.336-0", "activo": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("rut", response.context["form"].errors)
        self.assertEqual(Trabajador.objects.filter(empresa=self.empresa_a, rut=self.RUT).count(), 1)

    def test_operador_solo_ve_consumos_del_dia(self):
        Consumo.objects.create(trabajador=self.en_a, fecha=date(2026, 1, 5), operador=self.operador)
        Consumo.objects.create(trabajador=self.en_b, fecha=timezone.localdate(), operador=self.operador)
        self.client.force_login(self.operador)

        response = self.client.get(reverse("consumos:historial"), {"fecha": "2026-01-05"})

        self.assertEqual(response.context["consumos"].paginator.count, 1)
        self.assertEqual(response.context["consumos"][0].trabajador, self.en_b)
        self.assertNotContains(response, self.RUT)

    def test_rut_invalido_en_historial_no_muestra_resultados(self):
        Consumo.objects.create(trabajador=self.en_a, fecha=timezone.localdate(), operador=self.operador)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("consumos:historial"), {"rut": "12.492.336-9"})
        self.assertEqual(response.context["consumos"].paginator.count, 0)
        self.assertTrue(response.context["rut_error"])


class EscanerManualYContadorTests(TestCase):
    def setUp(self):
        self.operador = get_user_model().objects.create_user(username="mozo-man", password="x")
        Operador.objects.create(usuario=self.operador)
        self.empresa_a = Empresa.objects.create(nombre="A", rut="76111111-6", direccion="d", encargado_personal="e")
        self.empresa_b = Empresa.objects.create(
            nombre="B", rut="76222222-1", direccion="d", encargado_personal="e", almuerzos_diarios=2
        )
        self.en_a = Trabajador.objects.create(nombre="Pedro", apellido="Soto", rut="12492336-0", empresa=self.empresa_a)
        self.en_b = Trabajador.objects.create(nombre="Pedro", apellido="Soto", rut="12492336-0", empresa=self.empresa_b)
        self.client.force_login(self.operador)

    def test_buscar_rut_devuelve_una_opcion_por_empresa_con_su_cupo(self):
        Consumo.objects.create(trabajador=self.en_a, fecha=timezone.localdate(), operador=self.operador)
        response = self.client.get(reverse("consumos:buscar_rut"), {"rut": "12.492.336-0"})
        resultados = {r["company"]: (r["used"], r["quota"]) for r in response.json()["results"]}
        self.assertEqual(resultados, {"A": (1, 1), "B": (0, 2)})

    def test_buscar_rut_invalido_o_inexistente(self):
        self.assertEqual(self.client.get(reverse("consumos:buscar_rut"), {"rut": "12.492.336-9"}).status_code, 400)
        self.assertEqual(self.client.get(reverse("consumos:buscar_rut"), {"rut": "11.111.111-1"}).status_code, 404)

    def test_buscar_rut_excluye_desvinculados(self):
        self.en_b.activo = False
        self.en_b.eliminado_en = timezone.now()
        self.en_b.save(update_fields=["activo", "eliminado_en"])
        response = self.client.get(reverse("consumos:buscar_rut"), {"rut": "12492336-0"})
        self.assertEqual([r["company"] for r in response.json()["results"]], ["A"])

    def test_registro_manual_queda_marcado_y_respeta_cupo(self):
        def registrar():
            return self.client.post(
                reverse("consumos:escaner"), {"trabajador_id": self.en_a.pk}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
            ).json()

        primero = registrar()
        self.assertEqual(primero["status"], "registered")
        self.assertTrue(primero["manual"])
        self.assertEqual(primero["today_total"], 1)
        self.assertEqual(registrar()["status"], "duplicate")
        consumo = Consumo.objects.get(trabajador=self.en_a)
        self.assertEqual((consumo.metodo, consumo.operador), (Consumo.METODO_RUT, self.operador))

    def test_registro_por_qr_queda_marcado_como_qr(self):
        response = self.client.post(
            reverse("consumos:escaner"), {"token": str(self.en_b.token_qr)}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        ).json()
        self.assertFalse(response["manual"])
        self.assertEqual(Consumo.objects.get(trabajador=self.en_b).metodo, Consumo.METODO_QR)

    def test_pantalla_muestra_total_y_ultimos_del_operador(self):
        otro = get_user_model().objects.create_user(username="otro", password="x")
        Consumo.objects.create(trabajador=self.en_a, fecha=timezone.localdate(), operador=self.operador)
        Consumo.objects.create(trabajador=self.en_b, fecha=timezone.localdate(), operador=otro)
        response = self.client.get(reverse("consumos:escaner"))
        self.assertEqual(response.context["total_hoy"], 2)
        self.assertEqual([u["company"] for u in response.context["ultimos"]], ["A"])

    def test_operador_no_puede_buscar_sin_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("consumos:buscar_rut"), {"rut": "12492336-0"}).status_code, 302)


class VersionEstaticosTests(TestCase):
    def test_css_y_js_llevan_version_para_invalidar_cache(self):
        response = self.client.get(reverse("login"))
        version = response.context["static_version"]
        self.assertRegex(version, r"^[0-9a-f]{10}$")
        self.assertContains(response, f"css/app.css?v={version}")
        self.assertContains(response, f"js/app.js?v={version}")


class ConsumoPorLocalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.norte = Local.objects.create(nombre="Casino Norte", direccion="Calle 1")
        self.sur = Local.objects.create(nombre="Casino Sur", direccion="Calle 2")
        self.mozo_norte = User.objects.create_user(username="mozo-norte", password="x")
        Operador.objects.create(usuario=self.mozo_norte, local=self.norte)
        self.mozo_sur = User.objects.create_user(username="mozo-sur", password="x")
        Operador.objects.create(usuario=self.mozo_sur, local=self.sur)
        self.admin = User.objects.create_user(username="admin-local", password="x", is_staff=True)
        empresa = Empresa.objects.create(
            nombre="Empresa Local", rut="76111111-6", direccion="Dir",
            encargado_personal="RRHH", almuerzos_diarios=3,
        )
        self.trabajador = Trabajador.objects.create(
            nombre="Juan", apellido="Perez", rut="11111111-1", empresa=empresa
        )

    def escanear(self, usuario):
        self.client.force_login(usuario)
        return self.client.post(
            reverse("consumos:escaner"),
            {"token": str(self.trabajador.token_qr)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        ).json()

    def test_consumo_queda_en_el_local_del_operador(self):
        self.escanear(self.mozo_norte)
        self.escanear(self.mozo_sur)
        self.escanear(self.admin)

        locales = list(Consumo.objects.order_by("numero").values_list("local__nombre", flat=True))
        self.assertEqual(locales, ["Casino Norte", "Casino Sur", None])

    def test_historial_y_dashboard_por_local(self):
        self.escanear(self.mozo_norte)
        self.escanear(self.mozo_sur)
        self.escanear(self.mozo_sur)
        self.client.force_login(self.admin)

        response = self.client.get(reverse("consumos:historial"), {"local": self.sur.pk})
        self.assertEqual(response.context["consumos"].paginator.count, 2)

        dashboard = self.client.get(reverse("consumos:dashboard"))
        totales = {fila["local__nombre"]: fila["total"] for fila in dashboard.context["locales"]}
        self.assertEqual(totales, {"Casino Norte": 1, "Casino Sur": 2})

    def test_local_con_historial_no_se_elimina(self):
        self.escanear(self.mozo_norte)
        self.client.force_login(self.admin)

        response = self.client.post(reverse("locales:eliminar"), {"locales": [self.norte.pk]}, follow=True)

        self.assertTrue(Local.objects.filter(pk=self.norte.pk).exists())
        self.assertContains(response, "No se puede eliminar un local")

    def test_migracion_asigna_el_local_solo_si_hay_uno(self):
        from django.apps import apps
        migracion = import_module("consumos.migrations.0005_asignar_local_unico")
        sin_local = get_user_model().objects.create_user(username="mozo-antiguo", password="x")
        operador = Operador.objects.create(usuario=sin_local)

        migracion.asignar_local_unico(apps, None)
        operador.refresh_from_db()
        self.assertIsNone(operador.local)  # hay dos locales: no se puede saber cuál

        Operador.objects.exclude(pk=operador.pk).delete()
        self.sur.delete()
        migracion.asignar_local_unico(apps, None)
        operador.refresh_from_db()
        self.assertEqual(operador.local, self.norte)
