from django.urls import path

from . import views


app_name = "mesas"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("crear/", views.crear, name="crear"),
    path("qr/", views.pdf_qr, name="pdf"),
    path("<int:mesa_id>/estado/", views.cambiar_estado, name="estado"),
]
