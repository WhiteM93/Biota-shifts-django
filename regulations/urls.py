from django.urls import path

from .views import regulation_page

urlpatterns = [
    path("", regulation_page, name="regulations_page"),
]
