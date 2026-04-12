from django.urls import path

from .views import (
    regulation_page,
    regulations_api_meta,
    regulations_api_save,
    regulations_excel,
    regulations_pdf,
)

urlpatterns = [
    path("", regulation_page, name="regulations_page"),
    # Без суффикса .pdf/.xlsx в пути — иначе nginx может отдать статику вместо Django.
    path("download/xlsx/", regulations_excel, name="regulations_excel"),
    path("download/pdf/", regulations_pdf, name="regulations_pdf"),
    path("api/save/", regulations_api_save, name="regulations_api_save"),
    path("api/meta/", regulations_api_meta, name="regulations_api_meta"),
]
