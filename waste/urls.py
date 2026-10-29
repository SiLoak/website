from django.urls import path
from . import views

app_name = "waste"

urlpatterns = [
    path("submissions/", views.submission_history, name="submissions"),
    path("submissions/bulk-cancel/", views.bulk_cancel, name="bulk_cancel"),
    path("submissions/cancel/", views.cancel_entry, name="cancel_entry"),
    path("monitor/", views.monitor, name="monitor"),
    path("new/", views.new_submission, name="new"),
    path("dropoff/", views.dropoff_submission, name="dropoff"),
    path("<int:submission_id>/edit/", views.edit_submission, name="edit"),
    path("<int:submission_id>/cancel/", views.cancel_submission, name="cancel"),
    path("<int:submission_id>/", views.submission_detail, name="detail"),
]
