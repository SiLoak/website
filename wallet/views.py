
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect

from .forms import WithdrawalForm, DonationForm, IncentivePreferenceForm
from .models import Wallet, WalletTransaction, WithdrawalRequest, Donation
from .services import credit_wallet


def get_wallet(user):
    return Wallet.objects.get_or_create(user=user)[0]


@login_required(login_url="auth_page")
def wallet_index(request):
    wallet = get_wallet(request.user)

    if request.method == "POST" and request.POST.get("action") == "preference":
        form = IncentivePreferenceForm(request.POST)

        if form.is_valid():
            wallet.default_incentive = form.cleaned_data["default_incentive"]
            wallet.save(update_fields=["default_incentive", "updated_at"])
            messages.success(request, "Pilihan insentif berhasil disimpan.")
            return redirect("wallet:index")
    else:
        form = IncentivePreferenceForm(
            initial={"default_incentive": wallet.default_incentive}
        )

    return render(request, "wallet/wallet.html", {
        "active_item": "wallet",
        "wallet": wallet,
        "transactions": wallet.transactions.all()[:20],
        "last_withdrawal": wallet.withdrawals.first(),
        "preference_form": form,
        "preview_mode": False,
    })


@login_required(login_url="auth_page")
def withdraw_view(request):
    wallet = get_wallet(request.user)

    form = WithdrawalForm(
        request.POST or None,
        available_balance=wallet.balance,
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            amount = form.cleaned_data["amount"]

            if amount > wallet.balance:
                form.add_error(
                    "amount",
                    "Saldo berubah. Periksa kembali nominal."
                )
            else:
                wallet.balance -= amount
                wallet.total_withdrawn += amount
                wallet.save(
                    update_fields=[
                        "balance",
                        "total_withdrawn",
                        "updated_at",
                    ]
                )

                tx = WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type="withdrawal",
                    status="pending",
                    amount=amount,
                    description="Penarikan saldo",
                    destination=(
                        f"{form.cleaned_data['destination_name']} "
                        f"••••{form.cleaned_data['account_number'][-4:]}"
                    ),
                )

                WithdrawalRequest.objects.create(
                    wallet=wallet,
                    transaction=tx,
                    destination_type=form.cleaned_data["destination_type"],
                    destination_name=form.cleaned_data["destination_name"],
                    account_number=form.cleaned_data["account_number"],
                    account_holder=form.cleaned_data["account_holder"],
                    amount=amount,
                )

                messages.success(
                    request,
                    "Permintaan penarikan berhasil diajukan dan sedang diproses."
                )
                return redirect("wallet:index")

    return render(request, "wallet/withdraw.html", {
        "active_item": "wallet",
        "wallet": wallet,
        "form": form,
        "preview_mode": False,
    })

@login_required(login_url="auth_page")
def donation_view(request):
    wallet = get_wallet(request.user)

    form = DonationForm(
        request.POST or None,
        available_balance=wallet.balance,
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            amount = form.cleaned_data["amount"]

            if amount > wallet.balance:
                form.add_error(
                    "amount",
                    "Saldo berubah. Periksa kembali nominal."
                )
            else:
                wallet.balance -= amount
                wallet.total_donated += amount
                wallet.save(
                    update_fields=[
                        "balance",
                        "total_donated",
                        "updated_at",
                    ]
                )

                tx = WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type="donation",
                    status="success",
                    amount=amount,
                    description="Donasi insentif SiLoak",
                )

                Donation.objects.create(
                    wallet=wallet,
                    transaction=tx,
                    amount=amount,
                    message=form.cleaned_data.get("message", ""),
                )

                messages.success(
                    request,
                    "Terima kasih! Donasi berhasil dicatat."
                )
                return redirect("wallet:index")

    return render(request, "wallet/donate.html", {
        "active_item": "wallet",
        "wallet": wallet,
        "form": form,
        "preview_mode": False,
    })
