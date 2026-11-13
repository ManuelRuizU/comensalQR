from django.urls import path

from . import views


app_name = "consumos"

urlpatterns = [
	path("", views.dashboard, name="dashboard"),
	path("escaner/", views.escaner, name="escaner"),
	path("escaner/buscar/", views.buscar_por_rut, name="buscar_rut"),
	path("escaner/reservar/", views.reservar_porcion, name="reservar"),
	path("escaner/liberar/", views.liberar_reservas, name="liberar"),
	path("escaner/confirmar/", views.confirmar_pedido, name="confirmar"),
	path("historial/", views.historial, name="historial"),
	path("consumos/<int:consumo_id>/anular/", views.anular, name="anular"),
]
