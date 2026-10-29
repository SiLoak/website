
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404

from .forms import WithdrawalForm, DonationForm, IncentivePreferenceForm
from .models import Wallet, WalletTransaction, WithdrawalRequest, Donation
from decimal import Decimal, ROUND_HALF_UP

def get_wallet(user):
    return Wallet.objects.get_or_create(user=user)[0]

SERVICE_FEE_RATE = Decimal("0.02")

EWALLET_TRANSFER_FEES = {
    "GoPay": Decimal("1000.00"),
    "OVO": Decimal("1000.00"),
    "DANA": Decimal("500.00"),
    "ShopeePay": Decimal("1000.00"),
}

BANK_TRANSFER_FEES = {
    "BCA": Decimal("2500.00"),
    "BNI": Decimal("0.00"),
    "BRI": Decimal("2500.00"),
    "Mandiri": Decimal("2500.00"),
    "BSI": Decimal("2500.00"),
    "SeaBank": Decimal("2500.00"),
}

def calculate_withdrawal_fees(destination_type, destination_name, amount):
    service_fee = (amount * SERVICE_FEE_RATE).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    if destination_type == "ewallet":
        transfer_fee = EWALLET_TRANSFER_FEES[destination_name]
    else:
        transfer_fee = BANK_TRANSFER_FEES[destination_name]

    total_deduction = amount + transfer_fee + service_fee

    return transfer_fee, service_fee, total_deduction

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

    transactions = wallet.transactions.order_by("-created_at", "-pk")[:20]
    last_withdrawal = wallet.withdrawals.select_related(
        "transaction"
    ).order_by("-created_at", "-pk").first()

    return render(request, "wallet/wallet.html", {
        "active_item": "wallet",
        "wallet": wallet,
        "transactions": transactions,
        "last_withdrawal": last_withdrawal,
        "preference_form": form,
        "preview_mode": False,
    })

@login_required(login_url="auth_page")
def transaction_detail(request, pk):
    wallet = get_wallet(request.user)
    tx = get_object_or_404(WalletTransaction, pk=pk, wallet=wallet)
    withdrawal = None

    try:
        withdrawal = tx.withdrawal_request
    except WithdrawalRequest.DoesNotExist:
        pass

    total_deduction = tx.amount

    if (withdrawal and withdrawal.total_deduction is not None and withdrawal.total_deduction > 0):
        total_deduction = withdrawal.total_deduction

    type_labels = {
        WalletTransaction.Type.EARNING: "Insentif setoran",
        WalletTransaction.Type.WITHDRAWAL: "Penarikan saldo",
        WalletTransaction.Type.DONATION: "Donasi insentif",
        WalletTransaction.Type.REFUND: "Pengembalian dana",
    }

    return render(request, "wallet/transaction_detail.html", {
        "active_item": "wallet",
        "wallet": wallet,
        "tx": tx,
        "withdrawal": withdrawal,
        "type_label": type_labels.get(
            tx.transaction_type,
            tx.get_transaction_type_display()
            if hasattr(tx, "get_transaction_type_display")
            else tx.transaction_type,
        ),
        "total_deduction": total_deduction,
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
            destination_type = form.cleaned_data["destination_type"]
            destination_name = form.cleaned_data["destination_name"]

            transfer_fee, service_fee, total_deduction = (
                calculate_withdrawal_fees(
                    destination_type,
                    destination_name,
                    amount,
                )
            )

            if total_deduction > wallet.balance:
                form.add_error(
                    "amount",
                    "Saldo tidak cukup untuk nominal penarikan "
                    "beserta biaya transfer dan biaya layanan.",
                )
            else:
                wallet.balance -= total_deduction
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
                    transaction_type=WalletTransaction.Type.WITHDRAWAL,
                    status=WalletTransaction.Status.PENDING,
                    amount=amount,
                    description="Penarikan saldo",
                    destination=(
                        f"{destination_name} "
                        f"••••{form.cleaned_data['account_number'][-4:]}"
                    ),
                )

                WithdrawalRequest.objects.create(
                    wallet=wallet,
                    transaction=tx,
                    destination_type=destination_type,
                    destination_name=destination_name,
                    account_number=form.cleaned_data["account_number"],
                    account_holder=form.cleaned_data["account_holder"],
                    amount=amount,
                    transfer_fee=transfer_fee,
                    service_fee=service_fee,
                    total_deduction=total_deduction,
                )

                messages.success(
                    request,
                    "Permintaan penarikan berhasil diajukan "
                    "dan sedang diproses.",
                )
                return redirect("wallet:index")

    return render(request, "wallet/withdraw.html", {
        "active_item": "wallet",
        "wallet": wallet,
        "form": form,
        "preview_mode": False,
        "bank_transfer_fees": {
            key: int(value)
            for key, value in BANK_TRANSFER_FEES.items()
        },
        "ewallet_transfer_fees": {
            key: int(value)
            for key, value in EWALLET_TRANSFER_FEES.items()
        },
        "service_fee_rate": 2,
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
