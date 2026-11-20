from django.urls import path

from pickup import api_views

app_name = "api"

urlpatterns = [
  path("/", api_views.pickup_list, name="api_pickup_list"),
  path("collector/", api_views.collector_pickup_list, name="api_collector_pickup_list"),
  path("<uuid:pickup_id>/", api_views.pickup_detail, name="api_pickup_detail"),
  path("<uuid:pickup_id>/cancel/", api_views.pickup_cancel, name="api_pickup_cancel"),
  path("<uuid:pickup_id>/accept/", api_views.pickup_accept, name="api_pickup_accept"),
  path("<uuid:pickup_id>/status/", api_views.pickup_status, name="api_pickup_status"),
  path("<uuid:pickup_id>/weighing/", api_views.pickup_weighing, name="api_pickup_weighing"),
]