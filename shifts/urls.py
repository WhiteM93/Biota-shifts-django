from django.urls import path

from . import cabinet_views
from . import graph_views
from . import hours_views
from . import inventory_views
from . import product_views
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
    path("inventory/", inventory_views.inventory_view, name="inventory"),
    path("products/", product_views.products_list_view, name="products_list"),
    path("products/new/", product_views.product_create_view, name="product_create"),
    path("products/name-suggestions/", product_views.product_name_suggestions_view, name="product_name_suggestions"),
    path("products/<int:pk>/edit/", product_views.product_edit_view, name="product_edit"),
    path("products/<int:pk>/setups/new/", product_views.product_setup_create_view, name="product_setup_create"),
    path("products/<int:pk>/setups/<int:setup_pk>/edit/", product_views.product_setup_edit_view, name="product_setup_edit"),
    path("products/<int:pk>/setups/<int:setup_pk>/pdf/<str:mode>/", product_views.product_setup_pdf_export_view, name="product_setup_pdf_export"),
    path("products/<int:pk>/save-list-preview/", product_views.product_save_list_preview_view, name="product_save_list_preview"),
    path("products/<int:pk>/", product_views.product_detail_view, name="product_detail"),
    path("cabinet/", cabinet_views.cabinet_view, name="cabinet"),
    path("refresh-cache/", views.refresh_db_cache, name="refresh_cache"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/register/", views.register_view, name="register"),
    path("accounts/logout/", views.logout_view, name="logout"),
]
