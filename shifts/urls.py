from django.urls import path

from . import notify_api_views
from . import cabinet_views
from . import debug_log_views
from . import graph_mobile_views
from . import graph_views
from . import perf_diagnostic_views
from . import hours_views
from . import employee_payroll_views
from . import inventory_views
from . import payroll_views
from . import product_views
from . import skud_views
from . import forms_views
from . import machines_views
from . import views

urlpatterns = [
    path("", views.login_view, name="root"),
    path("home/", views.home_view, name="home"),
    path("graph/", graph_views.graph_view, name="graph"),
    path("graph/mobile/", graph_mobile_views.graph_mobile_view, name="graph_mobile"),
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
    path("machines/", machines_views.machines_view, name="machines"),
    path("calculator/", views.calculator_view, name="calculator"),
    path("forms/", forms_views.forms_view, name="forms"),
    path("forms/api/", forms_views.forms_api_list, name="forms_api_list"),
    path("forms/api/<int:pk>/", forms_views.forms_api_detail, name="forms_api_detail"),
    path("products/", product_views.products_list_view, name="products_list"),
    path("products/<int:pk>/delete/", product_views.product_delete_view, name="product_delete"),
    path("products/new/", product_views.product_create_view, name="product_create"),
    path("products/name-suggestions/", product_views.product_name_suggestions_view, name="product_name_suggestions"),
    path("products/<int:pk>/edit/", product_views.product_edit_view, name="product_edit"),
    path("products/<int:pk>/setups/<int:setup_pk>/edit/", product_views.product_setup_edit_view, name="product_setup_edit"),
    path("products/<int:pk>/setups/<int:setup_pk>/pdf/<str:mode>/", product_views.product_setup_pdf_export_view, name="product_setup_pdf_export"),
    path("products/<int:pk>/save-list-preview/", product_views.product_save_list_preview_view, name="product_save_list_preview"),
    path("products/<int:pk>/", product_views.product_detail_view, name="product_detail"),
    path("osnastki/", product_views.osnastka_list_view, name="osnastka_list"),
    path("osnastki/new/", product_views.osnastka_create_view, name="osnastka_create"),
    path("osnastki/<int:pk>/", product_views.osnastka_detail_view, name="osnastka_detail"),
    path("debug-log/ingest/", debug_log_views.debug_log_ingest, name="debug_log_ingest"),
    path("debug-log/list/", debug_log_views.debug_log_list, name="debug_log_list"),
    path("perf-diagnostic/ingest/", perf_diagnostic_views.perf_diagnostic_ingest, name="perf_diagnostic_ingest"),
    path("cabinet/perf-diagnostics/", perf_diagnostic_views.perf_diagnostics_view, name="perf_diagnostics"),
    path("api/notify/attendance/", notify_api_views.notify_attendance_trigger, name="notify_attendance_trigger"),
    path("cabinet/", cabinet_views.cabinet_view, name="cabinet"),
    path("cabinet/notifications/", cabinet_views.notifications_settings_view, name="cabinet_notifications"),
    path("cabinet/backups/", cabinet_views.schedule_backups_view, name="schedule_backups"),
    path("cabinet/backups/download/<str:filename>/", cabinet_views.schedule_backup_download, name="schedule_backup_download"),
    path("cabinet/inventory-backups/", cabinet_views.inventory_backups_view, name="inventory_backups"),
    path(
        "cabinet/inventory-backups/download/<str:filename>/",
        cabinet_views.inventory_backup_download,
        name="inventory_backup_download",
    ),
    path("cabinet/regulations-backups/", cabinet_views.regulations_backups_view, name="regulations_backups"),
    path(
        "cabinet/regulations-backups/download/<str:filename>/",
        cabinet_views.regulations_backup_download,
        name="regulations_backup_download",
    ),
    path("refresh-cache/", views.refresh_db_cache, name="refresh_cache"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/register/", views.register_view, name="register"),
    path("accounts/register/pending/", views.register_pending_view, name="register_pending"),
    path("accounts/register/legacy/", views.register_legacy_view, name="register_legacy"),
    path("accounts/verify-email/<str:token>/", views.verify_email_view, name="verify_email"),
    path("accounts/logout/", views.logout_view, name="logout"),
]
