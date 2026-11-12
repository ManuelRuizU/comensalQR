from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.views.generic.base import RedirectView
from django.urls import include, path

from consumos.pwa import service_worker
from operadores.views import ingreso


urlpatterns = [
    path(
        "admin/login/",
        RedirectView.as_view(pattern_name="login", query_string=True),
        name="admin_login_redirect",
    ),
    path("admin/", admin.site.urls),
    path("accounts/login/", ingreso, name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("account/login", RedirectView.as_view(pattern_name="login", permanent=False)),
    path("account/login/", RedirectView.as_view(pattern_name="login", permanent=False)),
    path("empresas/", include("empresas.urls")),
    path("locales/", include("locales.urls")),
    path("trabajadores/", include("trabajadores.urls")),
    path("operadores/", include("operadores.urls")),
    path("sw.js", service_worker, name="service_worker"),
    path("", include("consumos.urls")),
]
