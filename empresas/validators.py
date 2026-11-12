import re

from django.core.exceptions import ValidationError


def normalizar_rut(value):
    """Valida y devuelve el RUT chileno en formato 12345678-K."""
    raw = str(value or "").strip().upper().replace(".", "").replace(" ", "")
    match = re.fullmatch(r"(\d{1,8})-?([0-9K])", raw)
    if not match:
        raise ValidationError("Ingresa un RUT válido, por ejemplo 12.345.678-5.")

    cuerpo = match.group(1).lstrip("0") or "0"
    if cuerpo == "0":
        raise ValidationError("El RUT debe ser mayor que cero.")

    suma = 0
    factor = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1

    resultado = 11 - (suma % 11)
    verificador = "0" if resultado == 11 else "K" if resultado == 10 else str(resultado)
    if match.group(2) != verificador:
        raise ValidationError("El dígito verificador del RUT no es válido.")

    return f"{cuerpo}-{verificador}"


def validar_rut(value):
    normalizar_rut(value)
