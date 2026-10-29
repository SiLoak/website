from django.urls import path
from . import views

app_name = 'wallet'

urlpatterns = [
    path('', views.wallet_index, name='index'),
    path('withdraw/', views.withdraw_view, name='withdraw'),
    path("donate/",views.donation_view,name="donate"),
    path("transactions/<int:pk>/", views.transaction_detail, name="transaction_detail"),
]
