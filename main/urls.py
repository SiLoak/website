"""
URL configuration for main project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from main.views import (
    dashboard,
    history,
    landing_page,
    legal_page,
    profile,
    wallet,
)


urlpatterns = [ 
    path('admin/', admin.site.urls),
    path("", landing_page, name="landing_page"),
    path("dashboard/", dashboard, name="dashboard"),
    path("wallet/", wallet, name="wallet"),
    path("history/", history, name="history"),
    path("profile/", profile, name="profile"),
    path("terms/", legal_page, {"page": "terms"}, name="terms"),
    path("privacy/", legal_page, {"page": "privacy"}, name="privacy"),
    path('auth/', include('auth.urls')),
    path('location/', include('location.urls')),
    path('pickup/', include('pickup.urls')),
    path('waste/', include('waste.urls')),
]
