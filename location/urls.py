from django.urls import path
from . import views

app_name = "location"

urlpatterns = [
    path("", views.location_list, name="list"),
    path("api/points/", views.api_points, name="api_points"),
    path("api/points/<int:point_id>/", views.api_point_detail, name="api_point_detail"),
    path("api/points/<int:point_id>/address/", views.api_point_address, name="api_point_address"),
    path("api/geocode/", views.api_geocode, name="api_geocode"),
]
