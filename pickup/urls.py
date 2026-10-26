from django.urls import path
from . import views

app_name = "pickup"

urlpatterns = [
    path("", views.request_pickup, name="pickup_home"),
    path("new/", views.request_pickup, name="new"),
    path("<int:pickup_id>/", views.pickup_detail, name="detail"),
]
