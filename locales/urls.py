from django.urls import path

from . import views


app_name = "locales"

urlpatterns = [
    path("", views.lista_locales, name="lista"),
    path("nuevo/", views.crear_local, name="crear"),
    path("<int:pk>/editar/", views.editar_local, name="editar"),
    path("eliminar/", views.eliminar_locales, name="eliminar"),
]
