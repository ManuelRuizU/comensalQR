from django.urls import path

from . import views_despacho


app_name = "despacho"

urlpatterns = [
    path("", views_despacho.lista, name="lista"),
    path("confirmar/", views_despacho.confirmar, name="confirmar"),
]
