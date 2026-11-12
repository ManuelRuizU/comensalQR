import hashlib

from django.conf import settings


_ARCHIVOS_VERSIONADOS = ("css/app.css", "js/app.js")


def version_estaticos(request):
    """Versión de CSS/JS para invalidar la caché del navegador cuando cambian.

    Se agrega como ?v=... a las URLs: si el archivo cambia, cambia la URL y el
    teléfono descarga la versión nueva en vez de usar la copia guardada.
    """
    huella = hashlib.sha1()
    for ruta in _ARCHIVOS_VERSIONADOS:
        archivo = settings.BASE_DIR / "static" / ruta
        try:
            estado = archivo.stat()
        except OSError:
            continue
        huella.update(f"{ruta}:{estado.st_mtime_ns}:{estado.st_size}".encode())
    return {"static_version": huella.hexdigest()[:10]}
