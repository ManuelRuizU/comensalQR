"""Configuración aislada de pruebas: nunca conecta con PostgreSQL."""

import os

os.environ["DJANGO_DEBUG"] = "True"
os.environ["DJANGO_SECRET_KEY"] = "comensalqr-test-key-not-for-deployment-0000000000000000"

from .settings import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# EtiquetaMarmita usa una restricción única con nulls_distinct=False: PostgreSQL (producción
# y pruebas de concurrencia) la aplica; SQLite no la soporta y solo avisa.
SILENCED_SYSTEM_CHECKS = ["models.W047"]
