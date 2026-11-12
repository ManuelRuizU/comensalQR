from django.urls import path

from . import views


app_name = "consumos"

urlpatterns = [
	path("", views.dashboard, name="dashboard"),
	path("escaner/", views.escaner, name="escaner"),
	path("escaner/buscar/", views.buscar_por_rut, name="buscar_rut"),
	path("historial/", views.historial, name="historial"),
]
