from django.core.management.base import BaseCommand

from empresas.models import Empresa
from trabajadores.models import Trabajador


EMPRESAS_DEMO = {
    "Constructora ABC": [
        ("Juan", "Perez", "11111111-1"),
        ("Maria", "Soto", "11111112-0"),
        ("Pedro", "Diaz", "11111113-9"),
    ],
    "Transportes XYZ": [
        ("Carlos", "Rojas", "22222221-2"),
        ("Ana", "Fuentes", "22222222-0"),
        ("Luis", "Contreras", "22222223-9"),
    ],
    "Servicios del Sur": [
        ("Sofia", "Martinez", "33333331-3"),
        ("Diego", "Navarro", "33333332-1"),
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
                defaults={"activa": True},
            )
            if empresa_creada:
                empresas_creadas += 1

            for nombre, apellido, rut in trabajadores:
                _, trabajador_creado = Trabajador.objects.get_or_create(
                    rut=rut,
                    defaults={
                        "nombre": nombre,
                        "apellido": apellido,
                        "empresa": empresa,
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