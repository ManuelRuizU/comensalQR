from django.urls import path

from . import views


app_name = "administradores"

urlpatterns = [
    path("", views.lista_administradores, name="lista"),
    path("nuevo/", views.crear_administrador, name="crear"),
    path("<int:pk>/editar/", views.editar_administrador, name="editar"),
]
