from django.urls import path

from . import cabinet_views
from . import graph_views
from . import hours_views
from . import skud_views
from . import views

urlpatterns = [
    path("", views.login_view, name="root"),
    path("home/", views.home_view, name="home"),
    path("graph/", graph_views.graph_view, name="graph"),
    path("graph/download/", graph_views.graph_download, name="graph_download"),
    path("hours/", hours_views.hours_view, name="hours"),
    path("hours/excel/", hours_views.hours_excel, name="hours_excel"),
    path("hours/pdf/", hours_views.hours_pdf, name="hours_pdf"),
    path("skud/", skud_views.skud_view, name="skud"),
    path("skud/punches.csv", skud_views.skud_punches_csv, name="skud_punches_csv"),
    path("skud/stats.xlsx", skud_views.skud_stats_excel, name="skud_stats_excel"),
    path("skud/stats.csv", skud_views.skud_stats_csv, name="skud_stats_csv"),
    path("skud/stats.pdf", skud_views.skud_stats_pdf, name="skud_stats_pdf"),
    path("cabinet/", cabinet_views.cabinet_view, name="cabinet"),
    path("refresh-cache/", views.refresh_db_cache, name="refresh_cache"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/register/", views.register_view, name="register"),
    path("accounts/logout/", views.logout_view, name="logout"),
]
