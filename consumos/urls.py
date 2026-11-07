from django.urls import path

from . import views


app_name = "consumos"

urlpatterns = [
	path("", views.dashboard, name="dashboard"),
	path("escaner/", views.escaner, name="escaner"),
	path("historial/", views.historial, name="historial"),
]
