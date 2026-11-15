"""Documentos imprimibles del despacho (HTML para impresora normal; la térmica llega en la Fase 4).

Los QR llevan solo tokens de etiqueta (Pedido.token_etiqueta o EtiquetaMarmita.token).
Nunca se imprime el QR de un trabajador en etiquetas, guías ni hojas de reparto.
"""

from collections import OrderedDict

import qrcode
import qrcode.image.svg
from django.db import IntegrityError, transaction
from django.utils.safestring import mark_safe

from empresas.models import Empresa

from . import despacho
from .models import EtiquetaMarmita


def qr_svg(contenido):
    """QR en SVG en línea (nítido al imprimir, sin archivos temporales)."""
    imagen = qrcode.make(contenido, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    svg = imagen.to_string(encoding="unicode")
    return mark_safe(svg[svg.index("<svg"):])


def _lineas(pedido):
    return [str(item) for item in pedido.items.all()]


def etiquetas_individuales(pedidos):
    """Una etiqueta por pedido: nombre, empresa, platos, folio y QR del token de etiqueta."""
    return [
        {
            "nombre": str(pedido.consumo.trabajador),
            "empresa": str(pedido.consumo.trabajador.empresa),
            "lineas": _lineas(pedido),
            "folio": pedido.folio_texto,
            "qr": qr_svg(pedido.token_etiqueta),
        }
        for pedido in pedidos
    ]


def marmitas(empresa, local, fecha, pedidos):
    """Una marmita por plato y acompañamiento, con su cantidad, su token y los nombres para el reparto."""
    grupos = OrderedDict()
    for pedido in pedidos:
        for item in pedido.items.all():
            clave = (item.plato_id, item.acompanamiento_id)
            grupo = grupos.setdefault(clave, {"nombre": str(item), "plato": item.plato, "acompanamiento": item.acompanamiento, "trabajadores": []})
            grupo["trabajadores"].append(str(pedido.consumo.trabajador))
    resultado = []
    for (plato_id, acomp_id), grupo in sorted(grupos.items(), key=lambda par: (-len(par[1]["trabajadores"]), par[1]["nombre"])):
        etiqueta = _etiqueta_marmita(local, empresa, fecha, grupo["plato"], grupo["acompanamiento"])
        resultado.append({
            "nombre": grupo["nombre"],
            "cantidad": len(grupo["trabajadores"]),
            "trabajadores": sorted(grupo["trabajadores"]),
            "empresa": str(empresa),
            "token": etiqueta.token,
            "qr": qr_svg(etiqueta.token),
        })
    return resultado


def _etiqueta_marmita(local, empresa, fecha, plato, acompanamiento):
    try:
        with transaction.atomic():
            etiqueta, _ = EtiquetaMarmita.objects.get_or_create(
                empresa=empresa, fecha=fecha, plato=plato, acompanamiento=acompanamiento, defaults={"local": local}
            )
    except IntegrityError:  # otra impresión la creó al mismo tiempo
        etiqueta = EtiquetaMarmita.objects.get(empresa=empresa, fecha=fecha, plato=plato, acompanamiento=acompanamiento)
    return etiqueta


def datos_etiquetas(empresa, local, fecha):
    pedidos = list(despacho.pedidos_de_despacho(empresa, local, fecha))
    if empresa.tipo_envase == Empresa.ENVASE_MARMITA:
        return {"marmita": True, "marmitas": marmitas(empresa, local, fecha, pedidos), "total": len(pedidos)}
    return {"marmita": False, "etiquetas": etiquetas_individuales(pedidos), "total": len(pedidos)}


def datos_guia(empresa, local, fecha):
    """Guía de despacho: lista nominal, totales por plato y total de pedidos."""
    pedidos = list(despacho.pedidos_de_despacho(empresa, local, fecha))
    return {
        "filas": [
            {"nombre": str(p.consumo.trabajador), "rut": p.consumo.trabajador.rut, "lineas": _lineas(p), "folio": p.folio_texto}
            for p in pedidos
        ],
        "totales": despacho.totales_por_plato(pedidos),
        "total": len(pedidos),
    }
