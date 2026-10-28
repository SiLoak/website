from django.urls import path
from . import views

urlpatterns = [
    path("", views.auth_page, name="auth_page"),
    path("google/login/", views.google_login, name="google_login"),
    path("google/callback/", views.google_callback, name="google_callback"),
    path("complete-profile/", views.complete_profile, name="complete_profile"),
    path("logout/", views.logout_view, name="logout"),
]
