from django.urls import path

from pickup import views 

app_name = "pickup"

urlpatterns = [
  # Halaman
  path("", views.show_pickup_list, name="show_pickup_list"),
  path("collector/", views.show_collector_pickup_list, name="show_collector_pickup_list"),
  path("<uuid:pickup_id>/", views.show_pickup_detail, name="show_pickup_detail"),
  path("<uuid:pickup_id>/edit/", views.edit_pickup, name="edit"),

  # API (JSON)
  path("api/", views.get_pickup_json, name="get_pickup_json"),
  path("api/<uuid:pickup_id>/", views.get_pickup_detail_json, name="get_pickup_detail_json"),
  path("collector/api/", views.get_collector_pickup_json, name="get_collector_pickup_json"),

  # API (POST)
  path("new/", views.create_pickup_ajax, name="create_pickup_ajax"),
  path("<uuid:pickup_id>/cancel/", views.cancel_pickup_ajax, name="cancel_pickup_ajax"),
  path("<uuid:pickup_id>/accept/", views.accept_pickup_ajax, name="accept_pickup_ajax"),
  path("<uuid:pickup_id>/status/", views.update_pickup_status_ajax, name="update_pickup_status_ajax"),
  path("<uuid:pickup_id>/complete-weighing/", views.complete_weighing_ajax, name="complete_weighing_ajax"),
]