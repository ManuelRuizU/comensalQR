from django.urls import path

from . import views


app_name = "pedidos"

urlpatterns = [
    path("", views.pedidos_del_dia, name="lista"),
    path("item/<int:item_id>/cambiar/", views.cambiar_item, name="cambiar_item"),
]
