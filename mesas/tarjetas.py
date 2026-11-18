"""Tarjetas QR de mesa: mismo formato e impresión A4 que las de trabajador."""

from PIL import Image, ImageDraw

from trabajadores.tarjetas import (
    COLOR_BORDE,
    COLOR_FONDO,
    COLOR_MARCA,
    COLOR_SECUNDARIO,
    COLOR_TEXTO,
    _fuente,
    _texto_ajustado,
    imagen_qr,
    pdf_imprimible,
)


def tarjeta_mesa(mesa):
    """Tarjeta vertical de 1000x1220 px para pegar en la mesa."""
    tarjeta = Image.new("RGB", (1000, 1220), COLOR_FONDO)
    dibujo = ImageDraw.Draw(tarjeta)
    dibujo.rounded_rectangle((45, 45, 955, 1175), radius=28, fill="#ffffff", outline=COLOR_BORDE, width=4)
    dibujo.text((85, 85), "COMENSALQR", fill=COLOR_MARCA, font=_fuente(48, negrita=True))
    dibujo.text((85, 160), mesa.nombre.upper(), fill=COLOR_TEXTO, font=_texto_ajustado(dibujo, mesa.nombre.upper(), 830, 72, negrita=True))
    dibujo.text((85, 255), mesa.local.nombre, fill=COLOR_SECUNDARIO, font=_texto_ajustado(dibujo, mesa.local.nombre, 830, 34))
    lado_qr = 720
    tarjeta.paste(imagen_qr(mesa.token, lado_qr), ((1000 - lado_qr) // 2, 330))
    dibujo.text((85, 1090), "Código de mesa: lo escanea el garzón", fill=COLOR_SECUNDARIO, font=_fuente(26))
    return tarjeta


def pdf_mesas(mesas):
    return pdf_imprimible(mesas, dibujar=tarjeta_mesa)
