from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def wallet_index(request):
    return render(request, 'wallet/wallet.html', {"active_item": "wallet"})

@login_required
def withdraw_view(request):
    return render(request, 'wallet/withdraw.html', {"active_item": "wallet"})