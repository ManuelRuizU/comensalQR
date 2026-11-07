from django.urls import path

from . import views


app_name = "empresas"

urlpatterns = [
    path("", views.lista_empresas, name="lista"),
    path("nueva/", views.crear_empresa, name="crear"),
    path("eliminar/", views.eliminar_empresas, name="eliminar"),
    path("<int:pk>/", views.perfil_empresa, name="perfil"),
    path("<int:pk>/editar/", views.editar_empresa, name="editar"),
]
