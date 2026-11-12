from django.core.management.base import BaseCommand

from empresas.models import Empresa
from trabajadores.models import Trabajador


EMPRESAS_DATOS = {
    "Constructora ABC": {
        "rut": "76111111-6",
        "direccion": "Av. Principal 123",
        "encargado_personal": "Responsable Constructora ABC",
    },
    "Transportes XYZ": {
        "rut": "76222222-1",
        "direccion": "Av. Transporte 456",
        "encargado_personal": "Responsable Transportes XYZ",
    },
    "Servicios del Sur": {
        "rut": "76333333-7",
        "direccion": "Av. Sur 789",
        "encargado_personal": "Responsable Servicios del Sur",
    },
}


EMPRESAS_DEMO = {
    "Constructora ABC": [
        ("Juan", "Perez", "11111111-1"),
        ("Maria", "Soto", "11111112-K"),
        ("Pedro", "Diaz", "11111113-8"),
    ],
    "Transportes XYZ": [
        ("Carlos", "Rojas", "22222221-4"),
        ("Ana", "Fuentes", "22222222-2"),
        ("Luis", "Contreras", "22222223-0"),
    ],
    "Servicios del Sur": [
        ("Sofia", "Martinez", "33333331-7"),
        ("Diego", "Navarro", "33333332-5"),
    ],
}


class Command(BaseCommand):
    help = "Crea empresas y trabajadores de demostracion sin duplicarlos."

    def handle(self, *args, **options):
        empresas_creadas = 0
        trabajadores_creados = 0

        for nombre_empresa, trabajadores in EMPRESAS_DEMO.items():
            empresa, empresa_creada = Empresa.objects.get_or_create(
                nombre=nombre_empresa,
                defaults={
                    **EMPRESAS_DATOS[nombre_empresa],
                    "activa": True,
                },
            )
            if empresa_creada:
                empresas_creadas += 1

            for nombre, apellido, rut in trabajadores:
                _, trabajador_creado = Trabajador.objects.get_or_create(
                    rut=rut,
                    empresa=empresa,
                    eliminado_en__isnull=True,
                    defaults={
                        "nombre": nombre,
                        "apellido": apellido,
                        "activo": True,
                    },
                )
                if trabajador_creado:
                    trabajadores_creados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Siembra completada: {empresas_creadas} empresas nuevas y "
                f"{trabajadores_creados} trabajadores nuevos."
            )
        )
