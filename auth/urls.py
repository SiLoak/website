from django.urls import path
from . import views

urlpatterns = [
    path("", views.auth_page, name="auth_page"),
    path("google/login/", views.google_login, name="google_login"),
    path("google/callback/", views.google_callback, name="google_callback"),
]
