from django.urls import path

from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("graph/", views.graph_placeholder, name="graph"),
    path("hours/", views.hours_placeholder, name="hours"),
    path("skud/", views.skud_placeholder, name="skud"),
    path("cabinet/", views.cabinet_placeholder, name="cabinet"),
    path("refresh-cache/", views.refresh_db_cache, name="refresh_cache"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
]
