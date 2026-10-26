from django.urls import path
from . import views

app_name = "location"

urlpatterns = [
    path("", views.location_list, name="list"),
]
