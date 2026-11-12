from datetime import date

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from consumos.models import Consumo
from empresas.models import Empresa
from trabajadores.forms import TrabajadorForm
from trabajadores.models import TokenQRReservado, Trabajador
from operadores.models import Operador
from consumos.services import TrabajadorNoDisponible, registrar_consumo_diario


class EliminacionLogicaTrabajadorTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="clave-segura"
        )
        self.operador = get_user_model().objects.create_user(
            username="operador", password="clave-segura"
        )
        Operador.objects.create(usuario=self.operador)
        self.empresa = Empresa.objects.create(
            nombre="Constructora ABC",
            rut="76111111-6",
            direccion="Av. Principal 123",
            encargado_personal="Responsable",
        )
        self.trabajador = Trabajador.objects.create(
            nombre="Ana", apellido="Pérez", rut="11111111-1", empresa=self.empresa
        )
        self.url = reverse("trabajadores:eliminar", args=[self.empresa.pk])

    def test_administrador_elimina_logicamente_y_preserva_historial(self):
        consumo = Consumo.objects.create(
            trabajador=self.trabajador, fecha=date(2026, 10, 1), operador=self.operador
        )
        token = self.trabajador.token_qr
        self.client.force_login(self.admin)

        response = self.client.post(self.url, {"trabajadores": [self.trabajador.pk]})

        self.assertRedirects(response, reverse("trabajadores:por_empresa", args=[self.empresa.pk]))
        self.trabajador.refresh_from_db()
        self.assertFalse(self.trabajador.activo)
        self.assertIsNotNone(self.trabajador.eliminado_en)
        self.assertEqual(self.trabajador.eliminado_por, self.admin)
        self.assertEqual(self.trabajador.token_qr, token)
        self.assertTrue(Consumo.objects.filter(pk=consumo.pk).exists())

        historial = self.client.get(
            reverse("consumos:historial"), {"trabajador": self.trabajador.pk}
        )
        self.assertContains(historial, "Ana Pérez")

    def test_operador_no_puede_eliminar(self):
        self.client.force_login(self.operador)
        response = self.client.post(self.url, {"trabajadores": [self.trabajador.pk]})
        self.assertEqual(response.status_code, 302)
        self.trabajador.refresh_from_db()
        self.assertIsNone(self.trabajador.eliminado_en)

    def test_id_no_numerico_en_baja_masiva_no_causa_error(self):
        self.client.force_login(self.admin)

        response = self.client.post(self.url, {"trabajadores": "abc"})

        self.assertRedirects(response, reverse("trabajadores:por_empresa", args=[self.empresa.pk]))
        self.trabajador.refresh_from_db()
        self.assertIsNone(self.trabajador.eliminado_en)

    def test_eliminado_no_aparece_en_lista_vigente_y_si_en_filtro(self):
        self.trabajador.eliminado_en = self.trabajador.creado_en
        self.trabajador.activo = False
        self.trabajador.save(update_fields=["eliminado_en", "activo"])
        self.client.force_login(self.admin)

        response = self.client.get(reverse("trabajadores:lista"))
        self.assertNotContains(response, "Ana Pérez")
        response = self.client.get(reverse("trabajadores:lista"), {"estado": "eliminados"})
        self.assertContains(response, "Ana Pérez")

    def test_eliminado_no_registra_consumo_con_qr(self):
        self.trabajador.activo = False
        self.trabajador.eliminado_en = self.trabajador.creado_en
        self.trabajador.save(update_fields=["activo", "eliminado_en"])
        self.client.force_login(self.operador)

        response = self.client.post(
            reverse("consumos:escaner"),
            {"token": str(self.trabajador.token_qr)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Consumo.objects.filter(trabajador=self.trabajador).exists())

    def test_servicio_compartido_rechaza_trabajador_eliminado(self):
        self.trabajador.activo = False
        self.trabajador.eliminado_en = self.trabajador.creado_en
        self.trabajador.save(update_fields=["activo", "eliminado_en"])

        with self.assertRaises(TrabajadorNoDisponible):
            registrar_consumo_diario(self.trabajador.pk, self.operador)

        self.assertFalse(Consumo.objects.filter(trabajador=self.trabajador).exists())

    def test_uuid_qr_no_se_reutiliza(self):
        token = self.trabajador.token_qr
        self.trabajador.activo = False
        self.trabajador.eliminado_en = self.trabajador.creado_en
        self.trabajador.save(update_fields=["activo", "eliminado_en"])
        otro = Trabajador.objects.create(
            nombre="Luis", apellido="Rojas", rut="22222222-2", empresa=self.empresa
        )
        self.assertNotEqual(token, otro.token_qr)
        self.assertTrue(Trabajador.objects.filter(pk=self.trabajador.pk, token_qr=token).exists())

    def test_regenerar_qr_invalida_y_reserva_el_token_anterior(self):
        token_anterior = self.trabajador.token_qr
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("trabajadores:regenerar_qr", args=[self.trabajador.pk])
        )

        self.assertRedirects(response, reverse("trabajadores:por_empresa", args=[self.empresa.pk]))
        self.trabajador.refresh_from_db()
        self.assertNotEqual(self.trabajador.token_qr, token_anterior)
        self.assertTrue(
            TokenQRReservado.objects.filter(
                token=token_anterior,
                trabajador=self.trabajador,
                invalidado_por=self.admin,
            ).exists()
        )
        self.client.force_login(self.operador)
        scan_response = self.client.post(
            reverse("consumos:escaner"),
            {"token": str(token_anterior)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(scan_response.status_code, 400)

    def test_rut_se_valida_y_se_normaliza(self):
        self.trabajador.rut = "11.111.111-1"
        self.trabajador.save(update_fields=["rut"])
        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.rut, "11111111-1")

        with self.assertRaisesMessage(Exception, "dígito verificador"):
            Trabajador.objects.create(
                nombre="RUT", apellido="Inválido", rut="12.345.678-9", empresa=self.empresa
            )

    def test_rut_puede_reutilizarse_si_el_trabajador_anterior_fue_eliminado(self):
        otra_empresa = Empresa.objects.create(
            nombre="Transportes XYZ",
            rut="76111112-4",
            direccion="Av. Secundaria 456",
            encargado_personal="Responsable",
        )
        self.trabajador.eliminado_en = self.trabajador.creado_en
        self.trabajador.activo = False
        self.trabajador.save(update_fields=["eliminado_en", "activo"])

        nuevo_trabajador = Trabajador.objects.create(
            nombre="Ana",
            apellido="Pérez",
            rut=self.trabajador.rut,
            empresa=otra_empresa,
        )

        self.assertEqual(nuevo_trabajador.rut, "11111111-1")
        self.assertEqual(nuevo_trabajador.empresa, otra_empresa)

    def test_formulario_no_permite_reactivar_trabajador_eliminado(self):
        self.trabajador.activo = False
        self.trabajador.eliminado_en = self.trabajador.creado_en
        self.trabajador.save(update_fields=["activo", "eliminado_en"])

        form = TrabajadorForm(
            data={
                "nombre": self.trabajador.nombre,
                "apellido": self.trabajador.apellido,
                "rut": self.trabajador.rut,
                "empresa": self.empresa.pk,
                "activo": "on",
            },
            instance=self.trabajador,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("activo", form.errors)

    def test_formulario_no_ofrece_empresas_inactivas_al_crear(self):
        empresa_inactiva = Empresa.objects.create(
            nombre="Empresa Inactiva",
            rut="76333333-7",
            direccion="Calle 1",
            encargado_personal="Responsable",
            activa=False,
        )

        form = TrabajadorForm()

        self.assertNotIn(empresa_inactiva, form.fields["empresa"].queryset)

    def test_reactivacion_masiva_falla_en_la_restriccion_de_base_de_datos(self):
        self.trabajador.activo = False
        self.trabajador.eliminado_en = self.trabajador.creado_en
        self.trabajador.save(update_fields=["activo", "eliminado_en"])

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Trabajador.objects.filter(pk=self.trabajador.pk).update(activo=True)

    def test_admin_no_ofrece_eliminacion_fisica_ni_accion_masiva(self):
        request = RequestFactory().get("/admin/trabajadores/trabajador/")
        request.user = self.admin
        trabajador_admin = admin.site._registry[Trabajador]

        self.assertFalse(trabajador_admin.has_delete_permission(request))
        self.assertNotIn("delete_selected", trabajador_admin.get_actions(request))

        self.client.force_login(self.admin)
        delete_url = reverse("admin:trabajadores_trabajador_delete", args=[self.trabajador.pk])
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 403)

    def test_admin_no_reactiva_por_formulario_de_edicion(self):
        self.trabajador.activo = False
        self.trabajador.eliminado_en = self.trabajador.creado_en
        self.trabajador.save(update_fields=["activo", "eliminado_en"])
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin:trabajadores_trabajador_change", args=[self.trabajador.pk]),
            {
                "nombre": self.trabajador.nombre,
                "apellido": self.trabajador.apellido,
                "rut": self.trabajador.rut,
                "empresa": self.empresa.pk,
                "activo": "on",
                "_save": "Guardar",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.trabajador.refresh_from_db()
        self.assertFalse(self.trabajador.activo)

    def test_admin_no_cambia_empresa_si_hay_consumos_historicos(self):
        Consumo.objects.create(
            trabajador=self.trabajador,
            fecha=date(2026, 10, 2),
            operador=self.operador,
        )
        otra_empresa = Empresa.objects.create(
            nombre="Otra Empresa",
            rut="76222222-1",
            direccion="Calle 2",
            encargado_personal="Responsable",
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin:trabajadores_trabajador_change", args=[self.trabajador.pk]),
            {
                "nombre": self.trabajador.nombre,
                "apellido": self.trabajador.apellido,
                "rut": self.trabajador.rut,
                "empresa": otra_empresa.pk,
                "activo": "on",
                "_save": "Guardar",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.empresa, self.empresa)


class ImportacionYDescargaMasivaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username="admin-imp", password="x", is_staff=True)
        self.operador = User.objects.create_user(username="mozo-imp", password="x")
        Operador.objects.create(usuario=self.operador)
        self.empresa = Empresa.objects.create(
            nombre="Constructora ABC", rut="76111111-6", direccion="Av. 1",
            encargado_personal="RRHH", almuerzos_diarios=1,
        )
        self.client.force_login(self.admin)

    def subir(self, nombre, contenido):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return self.client.post(
            reverse("trabajadores:importar", args=[self.empresa.pk]),
            {"archivo": SimpleUploadedFile(nombre, contenido)},
        )

    def confirmar(self, response):
        return self.client.post(
            reverse("trabajadores:importar", args=[self.empresa.pk]),
            {"accion": "confirmar", "token": response.context["token"]},
        )

    def test_csv_con_punto_y_coma_y_tildes_cp1252_se_importa(self):
        contenido = (
            "Nombre;Apellidos;RUT;Almuerzos diarios\n"
            "José;Muñoz;12.492.336-0;2\n"
            "Ana;Pérez;11111111-1;\n"
        ).encode("cp1252")
        vista_previa = self.subir("nomina.csv", contenido)
        self.assertEqual(vista_previa.context["validas"], 2)
        self.assertEqual(Trabajador.objects.count(), 0)

        resultado = self.confirmar(vista_previa)

        self.assertEqual(resultado.status_code, 200)
        jose = Trabajador.objects.get(rut="12492336-0")
        self.assertEqual((jose.nombre, jose.apellido, jose.almuerzos_diarios), ("José", "Muñoz", 2))
        ana = Trabajador.objects.get(rut="11111111-1")
        self.assertIsNone(ana.almuerzos_diarios)
        self.assertEqual(ana.cupo_diario, 1)
        self.assertIn(f"trabajadores={jose.pk}", resultado.context["consulta"])

    def test_xlsx_se_importa(self):
        from io import BytesIO

        from openpyxl import Workbook

        libro = Workbook()
        hoja = libro.active
        hoja.append(["nombre", "apellido", "rut", "almuerzos_diarios"])
        hoja.append(["Pedro", "Soto", "12.492.336-0", 1])
        hoja.append([None, None, None, None])
        contenido = BytesIO()
        libro.save(contenido)

        vista_previa = self.subir("nomina.xlsx", contenido.getvalue())
        self.assertEqual(vista_previa.context["validas"], 1)
        self.confirmar(vista_previa)
        self.assertTrue(Trabajador.objects.filter(rut="12492336-0", empresa=self.empresa).exists())

    def test_errores_bloquean_toda_la_importacion(self):
        Trabajador.objects.create(nombre="Ya", apellido="Existe", rut="22222222-2", empresa=self.empresa)
        contenido = (
            "nombre,apellido,rut,almuerzos_diarios\n"
            "Bien,Valido,11111111-1,\n"
            "Mal,Digito,12.492.336-9,\n"
            "Repetido,Uno,33333331-7,\n"
            "Repetido,Dos,33.333.331-7,\n"
            "Existe,Ya,22222222-2,\n"
            ",SinNombre,44444444-4,\n"
            "Cupo,Malo,55555555-5,20\n"
        ).encode()
        response = self.subir("nomina.csv", contenido)

        self.assertIsNone(response.context["token"])
        self.assertEqual(response.context["con_errores"], 5)
        errores = {fila.numero: " ".join(fila.errores) for fila in response.context["filas"]}
        self.assertIn("verificador", errores[3])
        self.assertIn("repetido en el archivo (fila 4)", errores[5])
        self.assertIn("Ya existe", errores[6])
        self.assertIn("Falta el nombre", errores[7])
        self.assertIn("entre 1 y 10", errores[8])
        self.assertEqual(Trabajador.objects.count(), 1)

    def test_archivo_sin_columnas_obligatorias(self):
        response = self.subir("nomina.csv", b"nombre,correo\nAna,a@b.cl\n")
        self.assertIn("Faltan columnas obligatorias", response.context["error"])

    def test_formato_no_soportado(self):
        response = self.subir("nomina.txt", b"hola")
        self.assertIn("Formato no soportado", response.context["error"])

    def test_confirmar_dos_veces_no_duplica(self):
        vista_previa = self.subir("nomina.csv", b"nombre,apellido,rut\nAna,Perez,11111111-1\n")
        self.confirmar(vista_previa)
        segunda = self.confirmar(vista_previa)
        self.assertEqual(segunda.status_code, 302)
        self.assertEqual(Trabajador.objects.count(), 1)

    def test_operador_no_puede_importar_ni_descargar(self):
        self.client.force_login(self.operador)
        for url in (
            reverse("trabajadores:importar", args=[self.empresa.pk]),
            reverse("trabajadores:plantilla"),
            reverse("trabajadores:qr_pdf", args=[self.empresa.pk]),
            reverse("trabajadores:qr_zip", args=[self.empresa.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_plantilla_es_un_excel_con_encabezados(self):
        from io import BytesIO

        from openpyxl import load_workbook

        response = self.client.get(reverse("trabajadores:plantilla"))
        hoja = load_workbook(BytesIO(response.content)).worksheets[0]
        self.assertEqual([celda.value for celda in hoja[1]], ["nombre", "apellido", "rut", "almuerzos_diarios"])

    def crear_trabajadores(self, cantidad):
        ruts = ["11111111-1", "22222222-2", "33333331-7", "12492336-0", "11111112-K", "11111113-8", "22222221-4"]
        return [
            Trabajador.objects.create(nombre=f"Nombre{i}", apellido=f"Apellido{i}", rut=ruts[i], empresa=self.empresa)
            for i in range(cantidad)
        ]

    def test_zip_telefono_incluye_solo_activos_y_vigentes(self):
        import zipfile
        from io import BytesIO

        from PIL import Image

        activos = self.crear_trabajadores(4)
        activos[2].activo = False
        activos[2].save(update_fields=["activo"])
        activos[3].activo = False
        activos[3].eliminado_en = timezone.now()
        activos[3].save(update_fields=["activo", "eliminado_en"])

        response = self.client.get(reverse("trabajadores:qr_zip", args=[self.empresa.pk]))

        self.assertEqual(response["Content-Type"], "application/zip")
        with zipfile.ZipFile(BytesIO(response.content)) as archivo:
            nombres = sorted(archivo.namelist())
            self.assertEqual(nombres, ["apellido0-nombre0-constructora-abc.png", "apellido1-nombre1-constructora-abc.png"])
            self.assertEqual(Image.open(BytesIO(archivo.read(nombres[0]))).size, (1080, 1920))

    def test_descarga_solo_seleccionados(self):
        import zipfile
        from io import BytesIO

        trabajadores = self.crear_trabajadores(3)
        response = self.client.get(
            reverse("trabajadores:qr_zip", args=[self.empresa.pk]),
            {"trabajadores": [trabajadores[1].pk]},
        )
        with zipfile.ZipFile(BytesIO(response.content)) as archivo:
            self.assertEqual(archivo.namelist(), ["apellido1-nombre1-constructora-abc.png"])

    def test_pdf_tiene_6_tarjetas_por_hoja(self):
        self.crear_trabajadores(7)
        response = self.client.get(reverse("trabajadores:qr_pdf", args=[self.empresa.pk]))

        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-1.4"))
        self.assertIn(b"/Count 2", response.content)
        self.assertTrue(response.content.rstrip().endswith(b"%%EOF"))

    def test_sin_trabajadores_activos_redirige_con_aviso(self):
        response = self.client.get(reverse("trabajadores:qr_pdf", args=[self.empresa.pk]))
        self.assertRedirects(response, reverse("trabajadores:por_empresa", args=[self.empresa.pk]))

    def test_imagen_telefono_individual(self):
        from io import BytesIO

        from PIL import Image

        trabajador = self.crear_trabajadores(1)[0]
        response = self.client.get(reverse("trabajadores:qr_telefono", args=[trabajador.pk]))
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(Image.open(BytesIO(response.content)).size, (1080, 1920))


class EditarTrabajadorTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username="admin-edit", password="x", is_staff=True)
        self.operador = User.objects.create_user(username="mozo-edit", password="x")
        Operador.objects.create(usuario=self.operador)
        self.empresa = Empresa.objects.create(
            nombre="Empresa Edit", rut="76111111-6", direccion="Dir", encargado_personal="RRHH"
        )
        self.otra_empresa = Empresa.objects.create(
            nombre="Otra Empresa", rut="76222222-1", direccion="Dir", encargado_personal="RRHH"
        )
        self.trabajador = Trabajador.objects.create(
            nombre="Ana", apellido="Pérez", rut="11111111-1", empresa=self.empresa
        )
        self.url = reverse("trabajadores:editar", args=[self.trabajador.pk])

    def datos(self, **cambios):
        datos = {
            "empresa": self.empresa.pk,
            "nombre": "Ana",
            "apellido": "Pérez",
            "rut": "11111111-1",
            "almuerzos_diarios": "",
            "activo": "on",
        }
        datos.update(cambios)
        return {clave: valor for clave, valor in datos.items() if valor is not None}

    def test_asignar_excepcion_de_cupo_y_desactivar(self):
        self.client.force_login(self.admin)
        token = self.trabajador.token_qr

        response = self.client.post(self.url, self.datos(almuerzos_diarios=2, activo=None))

        self.assertRedirects(response, reverse("trabajadores:por_empresa", args=[self.empresa.pk]))
        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.cupo_diario, 2)
        self.assertFalse(self.trabajador.activo)
        self.assertEqual(self.trabajador.token_qr, token)

    def test_no_cambia_de_empresa_si_tiene_consumos(self):
        Consumo.objects.create(trabajador=self.trabajador, fecha=date(2026, 10, 1), operador=self.operador)
        self.client.force_login(self.admin)

        self.client.post(self.url, self.datos(empresa=self.otra_empresa.pk))

        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.empresa, self.empresa)

    def test_cambia_de_empresa_si_no_tiene_consumos(self):
        self.client.force_login(self.admin)

        self.client.post(self.url, self.datos(empresa=self.otra_empresa.pk))

        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.empresa, self.otra_empresa)

    def test_rut_duplicado_en_la_empresa_muestra_error(self):
        Trabajador.objects.create(nombre="Luis", apellido="Rojas", rut="22222222-2", empresa=self.empresa)
        self.client.force_login(self.admin)

        response = self.client.post(self.url, self.datos(rut="22.222.222-2"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("rut", response.context["form"].errors)

    def test_trabajador_eliminado_no_se_puede_editar(self):
        self.trabajador.activo = False
        self.trabajador.eliminado_en = timezone.now()
        self.trabajador.save(update_fields=["activo", "eliminado_en"])
        self.client.force_login(self.admin)

        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_operador_no_puede_editar(self):
        self.client.force_login(self.operador)

        response = self.client.post(self.url, self.datos(almuerzos_diarios=5))

        self.assertEqual(response.status_code, 302)
        self.trabajador.refresh_from_db()
        self.assertIsNone(self.trabajador.almuerzos_diarios)
