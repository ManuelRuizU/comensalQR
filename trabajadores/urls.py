from django.urls import path

from . import views


app_name = "trabajadores"

urlpatterns = [
    path("", views.lista_trabajadores, name="lista"),
    path("empresa/<int:empresa_id>/", views.lista_trabajadores_empresa, name="por_empresa"),
    path("empresa/<int:empresa_id>/eliminar/", views.eliminar_trabajadores, name="eliminar"),
    path("<int:trabajador_id>/qr/", views.descargar_qr, name="qr"),
    path("<int:trabajador_id>/qr/regenerar/", views.regenerar_qr, name="regenerar_qr"),
    path("<int:trabajador_id>/qr/telefono/", views.descargar_qr_telefono, name="qr_telefono"),
    path("empresa/<int:empresa_id>/qr/imprimir/", views.descargar_qr_pdf, name="qr_pdf"),
    path("empresa/<int:empresa_id>/qr/telefono/", views.descargar_qr_zip, name="qr_zip"),
    path("empresa/<int:empresa_id>/importar/", views.importar_trabajadores, name="importar"),
    path("importar/plantilla/", views.plantilla_importacion, name="plantilla"),
    path("nuevo/", views.crear_trabajador, name="crear"),
]
