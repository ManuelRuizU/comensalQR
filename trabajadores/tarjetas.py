"""Generación de tarjetas QR: impresa (PNG), imagen para teléfono, PDF A4 y ZIP.

Todas las variantes contienen el mismo token del trabajador, por lo que el papel
y la imagen del teléfono son intercambiables. Nada se guarda en disco: los
archivos se generan al momento de descargarlos.
"""

import zlib
import zipfile
from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from django.utils.text import slugify


COLOR_MARCA = "#087f73"
COLOR_TEXTO = "#17232c"
COLOR_SECUNDARIO = "#687782"
COLOR_FONDO = "#f4f7f6"
COLOR_BORDE = "#dce6e3"

_FUENTE = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_FUENTE_NEGRITA = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

# PDF A4 a 200 DPI: 6 tarjetas por hoja (2 columnas x 3 filas).
A4_PUNTOS = (595.28, 841.89)
A4_DPI = 200
A4_PIXELES = (round(A4_PUNTOS[0] / 72 * A4_DPI), round(A4_PUNTOS[1] / 72 * A4_DPI))
COLUMNAS, FILAS = 2, 3
TARJETAS_POR_HOJA = COLUMNAS * FILAS
MARGEN_HOJA = 90


def _fuente(tamano, negrita=False):
    ruta = _FUENTE_NEGRITA if negrita else _FUENTE
    if ruta.exists():
        return ImageFont.truetype(str(ruta), tamano)
    return ImageFont.load_default(size=tamano)


def _texto_ajustado(dibujo, texto, ancho_maximo, tamano, negrita=False, minimo=20):
    """Reduce el tamaño de la fuente hasta que el texto quepa en el ancho dado."""
    while tamano > minimo:
        fuente = _fuente(tamano, negrita)
        if dibujo.textlength(texto, font=fuente) <= ancho_maximo:
            return fuente
        tamano -= 2
    return _fuente(minimo, negrita)


def _imagen_qr(trabajador, lado):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=4,
    )
    qr.add_data(str(trabajador.token_qr))
    qr.make(fit=True)
    imagen = qr.make_image(fill_color=COLOR_TEXTO, back_color="#ffffff").convert("RGB")
    return imagen.resize((lado, lado), Image.NEAREST)


def tarjeta_impresa(trabajador):
    """Tarjeta vertical de 1000x1220 px pensada para imprimir."""
    tarjeta = Image.new("RGB", (1000, 1220), COLOR_FONDO)
    dibujo = ImageDraw.Draw(tarjeta)
    dibujo.rounded_rectangle((45, 45, 955, 1175), radius=28, fill="#ffffff", outline=COLOR_BORDE, width=4)
    dibujo.text((85, 85), "COMENSALQR", fill=COLOR_MARCA, font=_fuente(48, negrita=True))
    nombre = f"{trabajador.nombre} {trabajador.apellido}"
    dibujo.text((85, 175), nombre, fill=COLOR_TEXTO, font=_texto_ajustado(dibujo, nombre, 830, 48, negrita=True))
    empresa = trabajador.empresa.nombre
    dibujo.text((85, 245), empresa, fill=COLOR_SECUNDARIO, font=_texto_ajustado(dibujo, empresa, 830, 34))
    lado_qr = 720
    tarjeta.paste(_imagen_qr(trabajador, lado_qr), ((1000 - lado_qr) // 2, 330))
    dibujo.text((85, 1090), "Presentar este código para registrar el almuerzo", fill=COLOR_SECUNDARIO, font=_fuente(26))
    return tarjeta


def tarjeta_telefono(trabajador):
    """Imagen vertical de 1080x1920 px para guardar en la galería del teléfono."""
    ancho, alto = 1080, 1920
    imagen = Image.new("RGB", (ancho, alto), "#ffffff")
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rectangle((0, 0, ancho, 230), fill=COLOR_TEXTO)
    titulo = _fuente(64, negrita=True)
    dibujo.text(((ancho - dibujo.textlength("COMENSALQR", font=titulo)) / 2, 80), "COMENSALQR", fill="#ffffff", font=titulo)

    def centrado(texto, y, tamano, color, negrita=False):
        fuente = _texto_ajustado(dibujo, texto, ancho - 120, tamano, negrita)
        dibujo.text(((ancho - dibujo.textlength(texto, font=fuente)) / 2, y), texto, fill=color, font=fuente)

    centrado(f"{trabajador.nombre} {trabajador.apellido}", 320, 64, COLOR_TEXTO, negrita=True)
    centrado(trabajador.empresa.nombre, 420, 46, COLOR_SECUNDARIO)
    lado_qr = 900
    imagen.paste(_imagen_qr(trabajador, lado_qr), ((ancho - lado_qr) // 2, 540))
    centrado("Muestra esta imagen al registrar tu almuerzo", 1530, 40, COLOR_TEXTO)
    centrado("Sube el brillo de la pantalla si no se lee", 1600, 34, COLOR_SECUNDARIO)
    dibujo.rectangle((0, alto - 40, ancho, alto), fill=COLOR_MARCA)
    return imagen


def png_bytes(imagen):
    contenido = BytesIO()
    imagen.save(contenido, format="PNG", optimize=True)
    return contenido.getvalue()


def nombre_archivo_trabajador(trabajador):
    return slugify(f"{trabajador.apellido}-{trabajador.nombre}-{trabajador.empresa.nombre}") or f"trabajador-{trabajador.pk}"


def zip_telefono(trabajadores):
    """ZIP con una imagen para teléfono por trabajador."""
    contenido = BytesIO()
    usados = set()
    with zipfile.ZipFile(contenido, "w", compression=zipfile.ZIP_DEFLATED) as archivo:
        for trabajador in trabajadores:
            base = nombre_archivo_trabajador(trabajador)
            nombre, sufijo = base, 2
            while nombre in usados:
                nombre = f"{base}-{sufijo}"
                sufijo += 1
            usados.add(nombre)
            archivo.writestr(f"{nombre}.png", png_bytes(tarjeta_telefono(trabajador)))
    return contenido.getvalue()


def _hoja_a4(trabajadores):
    hoja = Image.new("RGB", A4_PIXELES, "#ffffff")
    dibujo = ImageDraw.Draw(hoja)
    ancho_celda = (A4_PIXELES[0] - 2 * MARGEN_HOJA) // COLUMNAS
    alto_celda = (A4_PIXELES[1] - 2 * MARGEN_HOJA) // FILAS
    relleno = 24
    escala = min((ancho_celda - 2 * relleno) / 1000, (alto_celda - 2 * relleno) / 1220)
    tamano = (round(1000 * escala), round(1220 * escala))

    # Líneas de corte punteadas entre tarjetas y en el borde del área útil.
    for columna in range(COLUMNAS + 1):
        x = MARGEN_HOJA + columna * ancho_celda
        for y in range(MARGEN_HOJA, A4_PIXELES[1] - MARGEN_HOJA, 24):
            dibujo.line((x, y, x, y + 12), fill="#b8c4c0", width=2)
    for fila in range(FILAS + 1):
        y = MARGEN_HOJA + fila * alto_celda
        for x in range(MARGEN_HOJA, A4_PIXELES[0] - MARGEN_HOJA, 24):
            dibujo.line((x, y, x + 12, y), fill="#b8c4c0", width=2)

    for indice, trabajador in enumerate(trabajadores):
        columna, fila = indice % COLUMNAS, indice // COLUMNAS
        tarjeta = tarjeta_impresa(trabajador).resize(tamano, Image.LANCZOS)
        x = MARGEN_HOJA + columna * ancho_celda + (ancho_celda - tamano[0]) // 2
        y = MARGEN_HOJA + fila * alto_celda + (alto_celda - tamano[1]) // 2
        hoja.paste(tarjeta, (x, y))
    return hoja


def pdf_imprimible(trabajadores):
    """PDF A4 con 6 tarjetas por hoja.

    Se escribe un PDF mínimo a mano, comprimiendo cada hoja sin pérdida (Flate)
    en cuanto se dibuja, para no mantener todas las hojas en memoria.
    """
    trabajadores = list(trabajadores)
    hojas = [
        trabajadores[i:i + TARJETAS_POR_HOJA]
        for i in range(0, len(trabajadores), TARJETAS_POR_HOJA)
    ] or [[]]

    salida = BytesIO()
    desplazamientos = {}

    def escribir_objeto(numero, cuerpo, flujo=None):
        desplazamientos[numero] = salida.tell()
        salida.write(f"{numero} 0 obj\n".encode())
        salida.write(cuerpo)
        if flujo is not None:
            salida.write(b"\nstream\n")
            salida.write(flujo)
            salida.write(b"\nendstream")
        salida.write(b"\nendobj\n")

    salida.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    ancho_pt, alto_pt = A4_PUNTOS
    paginas = []
    for indice, grupo in enumerate(hojas):
        pagina, imagen, contenido = 3 + 3 * indice, 4 + 3 * indice, 5 + 3 * indice
        paginas.append(pagina)
        hoja = _hoja_a4(grupo)
        datos = zlib.compress(hoja.tobytes(), 6)
        ancho_px, alto_px = hoja.size
        del hoja
        escribir_objeto(
            imagen,
            (
                f"<< /Type /XObject /Subtype /Image /Width {ancho_px} /Height {alto_px} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
                f"/Length {len(datos)} >>"
            ).encode(),
            datos,
        )
        dibujo = f"q {ancho_pt:.2f} 0 0 {alto_pt:.2f} 0 0 cm /Im0 Do Q".encode()
        escribir_objeto(contenido, f"<< /Length {len(dibujo)} >>".encode(), dibujo)
        escribir_objeto(
            pagina,
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {ancho_pt:.2f} {alto_pt:.2f}] "
                f"/Resources << /XObject << /Im0 {imagen} 0 R >> >> /Contents {contenido} 0 R >>"
            ).encode(),
        )

    hijos = " ".join(f"{numero} 0 R" for numero in paginas)
    escribir_objeto(2, f"<< /Type /Pages /Kids [{hijos}] /Count {len(paginas)} >>".encode())
    escribir_objeto(1, b"<< /Type /Catalog /Pages 2 0 R >>")

    total = max(desplazamientos) + 1
    inicio_xref = salida.tell()
    salida.write(f"xref\n0 {total}\n".encode())
    salida.write(b"0000000000 65535 f \n")
    for numero in range(1, total):
        salida.write(f"{desplazamientos[numero]:010d} 00000 n \n".encode())
    salida.write(
        f"trailer\n<< /Size {total} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n".encode()
    )
    return salida.getvalue()
