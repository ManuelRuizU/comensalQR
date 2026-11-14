from django.urls import path

from . import views


app_name = "menus"

urlpatterns = [
    path("", views.menu_dia, name="menu_dia"),
    path("crear/", views.crear_menu, name="crear"),
    path("tiempos/", views.tiempos, name="tiempos"),
    path("hoy/disponibilidad/", views.disponibilidad_hoy, name="disponibilidad_hoy"),
    path("<int:menu_id>/accion/", views.accion_menu, name="accion"),
    path("<int:menu_id>/disponibilidad/", views.disponibilidad_admin, name="disponibilidad"),
    path("<int:menu_id>/cierre/", views.informe_cierre, name="cierre"),
]
