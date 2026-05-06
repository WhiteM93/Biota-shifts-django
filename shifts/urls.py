from django.urls import path

from . import cabinet_views
from . import graph_views
from . import plan_contract_views
from . import plan_views
from . import hours_views
from . import employee_payroll_views
from . import inventory_views
from . import payroll_views
from . import product_views
from . import skud_views
from . import views

urlpatterns = [
    path("", views.login_view, name="root"),
    path("home/", views.home_view, name="home"),
    path("plan/", plan_views.plan_index, name="plan"),
    path(
        "plan/by-department/<slug:slug>/",
        plan_views.plan_department_planning,
        name="plan_department_planning",
    ),
    path("plan/articles/name-suggestions/", plan_views.plan_product_name_suggestions_view, name="plan_product_name_suggestions"),
    path("plan/articles/new/", plan_views.plan_article_edit, {"pk": None}, name="plan_article_new"),
    path("plan/articles/<int:pk>/delete/", plan_views.plan_article_delete, name="plan_article_delete"),
    path("plan/articles/<int:pk>/edit/", plan_views.plan_article_edit, name="plan_article_edit"),
    path("plan/articles/<int:pk>/", plan_views.plan_article_detail, name="plan_article_detail"),
    path("plan/contracts/new/", plan_contract_views.plan_contract_edit, {"pk": None}, name="plan_contract_new"),
    path(
        "plan/contracts/<int:contract_pk>/articles/<int:product_pk>/",
        plan_contract_views.plan_contract_article_detail,
        name="plan_contract_article_detail",
    ),
    path("plan/contracts/<int:pk>/delete/", plan_contract_views.plan_contract_delete, name="plan_contract_delete"),
    path("plan/contracts/<int:pk>/edit/", plan_contract_views.plan_contract_edit, name="plan_contract_edit"),
    path("plan/contracts/<int:pk>/", plan_contract_views.plan_contract_detail, name="plan_contract_detail"),
    path("plan/contracts/", plan_contract_views.plan_contract_index, name="plan_contracts"),
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
    path(
        "inventory/employees/<str:emp_code>/",
        employee_payroll_views.employee_payroll_detail_view,
        name="employee_payroll_detail",
    ),
    path(
        "inventory/payroll/<str:emp_code>/",
        payroll_views.payroll_settlement_view,
        name="payroll_settlement",
    ),
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
