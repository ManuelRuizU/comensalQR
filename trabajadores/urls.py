from django.urls import path

from . import views


app_name = "trabajadores"

urlpatterns = [
    path("", views.lista_trabajadores, name="lista"),
    path("empresa/<int:empresa_id>/", views.lista_trabajadores_empresa, name="por_empresa"),
    path("empresa/<int:empresa_id>/eliminar/", views.eliminar_trabajadores, name="eliminar"),
    path("<int:trabajador_id>/qr/", views.descargar_qr, name="qr"),
    path("nuevo/", views.crear_trabajador, name="crear"),
]
