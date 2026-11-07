from django.urls import path

from . import views


app_name = "operadores"

urlpatterns = [
    path("", views.lista_operadores, name="lista"),
    path("nuevo/", views.crear_operador, name="crear"),
]
