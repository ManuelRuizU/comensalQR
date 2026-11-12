import hashlib
import hmac
import ipaddress
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import IntentoAcceso


MAX_INTENTOS_POR_CUENTA_IP = 5
MAX_INTENTOS_POR_CUENTA = 10
MAX_INTENTOS_POR_IP = 20
VENTANA = timedelta(minutes=15)
DURACION_BLOQUEO = timedelta(minutes=15)
MENSAJE_LOGIN_INVALIDO = "Usuario o contraseña incorrectos o cuenta no disponible."


def _huella(clave):
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        clave.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _client_ip(request):
    remote_addr = request.META.get("REMOTE_ADDR") or "unknown"
    header = getattr(settings, "LOGIN_RATE_LIMIT_IP_HEADER", None)
    trusted_proxies = getattr(settings, "LOGIN_RATE_LIMIT_TRUSTED_PROXY_IPS", ())
    if header and remote_addr in trusted_proxies:
        forwarded_ip = request.META.get(header, "").strip()
        try:
            return str(ipaddress.ip_address(forwarded_ip))
        except ValueError:
            pass
    return remote_addr


def _claves(request, username):
    ip = _client_ip(request)
    cuenta = (username or "").strip().casefold()
    return {
        _huella(f"ip:{ip}"): MAX_INTENTOS_POR_IP,
        _huella(f"cuenta-ip:{ip}:{cuenta}"): MAX_INTENTOS_POR_CUENTA_IP,
        _huella(f"cuenta:{cuenta}"): MAX_INTENTOS_POR_CUENTA,
    }


def _obtener_bloqueado(clave, ahora):
    try:
        intento = IntentoAcceso.objects.select_for_update().get(clave=clave)
    except IntentoAcceso.DoesNotExist:
        try:
            with transaction.atomic():
                intento = IntentoAcceso.objects.create(clave=clave, ventana_desde=ahora)
        except IntegrityError:
            intento = IntentoAcceso.objects.select_for_update().get(clave=clave)
    if ahora - intento.ventana_desde >= VENTANA:
        intento.intentos = 0
        intento.ventana_desde = ahora
        intento.bloqueado_hasta = None
        intento.save(update_fields=["intentos", "ventana_desde", "bloqueado_hasta", "actualizado_en"])
    return intento


def reservar_intento(request, username):
    """Reserva el intento antes de autenticar para cerrar carreras concurrentes."""
    ahora = timezone.now()
    claves = _claves(request, username)
    with transaction.atomic():
        IntentoAcceso.objects.filter(
            actualizado_en__lt=ahora - timedelta(days=30)
        ).delete()
        intentos = {
            clave: _obtener_bloqueado(clave, ahora)
            for clave in claves
        }
        bloqueado = False
        for clave, intento in intentos.items():
            if intento.bloqueado_hasta and intento.bloqueado_hasta > ahora:
                bloqueado = True
            elif intento.intentos >= claves[clave]:
                intento.bloqueado_hasta = ahora + DURACION_BLOQUEO
                intento.save(update_fields=["bloqueado_hasta", "actualizado_en"])
                bloqueado = True
        if bloqueado:
            return False
        for intento in intentos.values():
            intento.intentos += 1
            intento.save(update_fields=["intentos", "actualizado_en"])
    return True


def registrar_fallo(request, username):
    ahora = timezone.now()
    with transaction.atomic():
        for clave, max_intentos in _claves(request, username).items():
            intento = _obtener_bloqueado(clave, ahora)
            if intento.intentos >= max_intentos:
                intento.bloqueado_hasta = ahora + DURACION_BLOQUEO
                intento.save(update_fields=["bloqueado_hasta", "actualizado_en"])


def limpiar_fallos_cuenta(request, username):
    ip = _client_ip(request)
    cuenta = (username or "").strip().casefold()
    with transaction.atomic():
        IntentoAcceso.objects.filter(clave=_huella(f"cuenta-ip:{ip}:{cuenta}")).delete()
        IntentoAcceso.objects.filter(clave=_huella(f"cuenta:{cuenta}")).delete()
        clave_ip = _huella(f"ip:{ip}")
        try:
            intento_ip = IntentoAcceso.objects.select_for_update().get(clave=clave_ip)
        except IntentoAcceso.DoesNotExist:
            return
        if intento_ip.bloqueado_hasta and intento_ip.bloqueado_hasta > timezone.now():
            return
        intento_ip.intentos = max(0, intento_ip.intentos - 1)
        intento_ip.save(update_fields=["intentos", "actualizado_en"])
