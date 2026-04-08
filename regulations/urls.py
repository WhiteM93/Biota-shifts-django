from django.urls import path

from .views import regulation_page, regulations_api_save

urlpatterns = [
    path("", regulation_page, name="regulations_page"),
    path("api/save/", regulations_api_save, name="regulations_api_save"),
]
