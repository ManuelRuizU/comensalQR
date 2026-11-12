"""Lectura y validación de la nómina de trabajadores desde Excel (.xlsx) o CSV."""

import csv
import io
import unicodedata
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError

from empresas.validators import normalizar_rut

from .models import Trabajador


TAMANO_MAXIMO_BYTES = 2 * 1024 * 1024
FILAS_MAXIMAS = 2000
COLUMNAS_PLANTILLA = ["nombre", "apellido", "rut", "almuerzos_diarios"]
# Encabezados aceptados (en minúsculas, sin tildes y con "_" como espacio).
_ALIAS = {
    "nombre": "nombre",
    "nombres": "nombre",
    "apellido": "apellido",
    "apellidos": "apellido",
    "rut": "rut",
    "almuerzos diarios": "almuerzos_diarios",
    "almuerzos": "almuerzos_diarios",
    "cupo": "almuerzos_diarios",
    "cupo diario": "almuerzos_diarios",
}


class ArchivoInvalido(Exception):
    """El archivo no se puede leer o no tiene las columnas requeridas."""


@dataclass
class FilaImportacion:
    numero: int
    nombre: str = ""
    apellido: str = ""
    rut: str = ""
    almuerzos_diarios: int | None = None
    errores: list = field(default_factory=list)

    @property
    def valida(self):
        return not self.errores

    def como_dict(self):
        return {
            "nombre": self.nombre,
            "apellido": self.apellido,
            "rut": self.rut,
            "almuerzos_diarios": self.almuerzos_diarios,
        }


def _normalizar_encabezado(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
    return " ".join(texto.lower().replace("_", " ").split())


def _celda_texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def _leer_xlsx(contenido):
    from openpyxl import load_workbook

    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as error:  # openpyxl lanza distintos tipos según el daño del archivo
        raise ArchivoInvalido("No se pudo leer el archivo Excel. Verifica que sea un .xlsx válido.") from error
    try:
        hoja = libro.worksheets[0]
        return [[_celda_texto(celda) for celda in fila] for fila in hoja.iter_rows(values_only=True)]
    finally:
        libro.close()


def _leer_csv(contenido):
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            texto = contenido.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ArchivoInvalido("No se pudo leer el archivo CSV: codificación no reconocida.")
    primera_linea = texto.splitlines()[0] if texto.strip() else ""
    delimitador = max(";,\t", key=primera_linea.count) if primera_linea else ","
    return [[celda.strip() for celda in fila] for fila in csv.reader(io.StringIO(texto), delimiter=delimitador)]


def leer_archivo(archivo):
    """Devuelve las filas del archivo como listas de texto (incluye el encabezado)."""
    if archivo.size > TAMANO_MAXIMO_BYTES:
        raise ArchivoInvalido("El archivo supera el tamaño máximo de 2 MB.")
    nombre = (archivo.name or "").lower()
    contenido = archivo.read()
    if nombre.endswith(".xlsx"):
        return _leer_xlsx(contenido)
    if nombre.endswith(".csv"):
        return _leer_csv(contenido)
    raise ArchivoInvalido("Formato no soportado. Usa un archivo .xlsx o .csv.")


def validar_filas(filas, empresa):
    """Valida la nómina contra las reglas de Trabajador para la empresa dada."""
    filas = [fila for fila in filas if any(celda for celda in fila)]
    if not filas:
        raise ArchivoInvalido("El archivo está vacío.")

    encabezado = [_ALIAS.get(_normalizar_encabezado(celda)) for celda in filas[0]]
    faltantes = [columna for columna in ("nombre", "apellido", "rut") if columna not in encabezado]
    if faltantes:
        raise ArchivoInvalido(
            "Faltan columnas obligatorias: " + ", ".join(faltantes)
            + ". Usa la plantilla (nombre, apellido, rut, almuerzos_diarios)."
        )
    indices = {columna: encabezado.index(columna) for columna in set(encabezado) if columna}

    datos = filas[1:]
    if not datos:
        raise ArchivoInvalido("El archivo no tiene trabajadores, solo el encabezado.")
    if len(datos) > FILAS_MAXIMAS:
        raise ArchivoInvalido(f"El archivo supera el máximo de {FILAS_MAXIMAS} trabajadores.")

    ruts_existentes = set(
        Trabajador.objects.filter(empresa=empresa, eliminado_en__isnull=True).values_list("rut", flat=True)
    )
    ruts_en_archivo = {}
    resultado = []
    for posicion, celdas in enumerate(datos, start=2):
        def valor(columna):
            indice = indices.get(columna)
            return celdas[indice].strip() if indice is not None and indice < len(celdas) else ""

        fila = FilaImportacion(numero=posicion, nombre=valor("nombre"), apellido=valor("apellido"))
        for campo in ("nombre", "apellido"):
            texto = getattr(fila, campo)
            if not texto:
                fila.errores.append(f"Falta el {campo}.")
            elif len(texto) > 100:
                fila.errores.append(f"El {campo} supera los 100 caracteres.")

        rut_original = valor("rut")
        fila.rut = rut_original
        if not rut_original:
            fila.errores.append("Falta el RUT.")
        else:
            try:
                fila.rut = normalizar_rut(rut_original)
            except ValidationError as error:
                fila.errores.append(error.messages[0])
            else:
                if fila.rut in ruts_existentes:
                    fila.errores.append("Ya existe un trabajador vigente con este RUT en la empresa.")
                elif fila.rut in ruts_en_archivo:
                    fila.errores.append(f"RUT repetido en el archivo (fila {ruts_en_archivo[fila.rut]}).")
                else:
                    ruts_en_archivo[fila.rut] = posicion

        cupo = valor("almuerzos_diarios")
        if cupo:
            try:
                numero = float(cupo.replace(",", "."))
                if not numero.is_integer() or not 1 <= numero <= 10:
                    raise ValueError
                fila.almuerzos_diarios = int(numero)
            except ValueError:
                fila.errores.append("Almuerzos diarios debe ser un número entero entre 1 y 10, o quedar vacío.")
        resultado.append(fila)
    return resultado


def plantilla_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Trabajadores"
    hoja.append(COLUMNAS_PLANTILLA)
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    for columna, ancho in zip("ABCD", (24, 24, 16, 20)):
        hoja.column_dimensions[columna].width = ancho

    ayuda = libro.create_sheet("Instrucciones")
    for linea in (
        ["Completa la hoja «Trabajadores»: una fila por trabajador, sin modificar el encabezado."],
        ["nombre y apellido: obligatorios."],
        ["rut: obligatorio, con dígito verificador (ej. 12.345.678-5 o 12345678-5)."],
        ["almuerzos_diarios: opcional. Si queda vacío se usa el cupo de la empresa."],
        ["Si alguna fila tiene errores no se importa nada; corrige el archivo y vuelve a subirlo."],
    ):
        ayuda.append(linea)
    ayuda.column_dimensions["A"].width = 100

    contenido = io.BytesIO()
    libro.save(contenido)
    return contenido.getvalue()
