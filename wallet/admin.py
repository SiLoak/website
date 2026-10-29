
from django.contrib import admin, messages
from django.db import transaction

from .models import Wallet, WalletTransaction, WithdrawalRequest, Donation

@admin.action(description="Tandai penarikan sebagai Berhasil")
def mark_withdrawals_success(modeladmin, request, queryset):
    success_count = 0
    skipped_count = 0

    for withdrawal in queryset:
        with transaction.atomic():
            withdrawal = (WithdrawalRequest.objects.select_for_update().select_related("transaction").get(pk=withdrawal.pk))

            if withdrawal.status != "processing":
                skipped_count += 1
                continue

            tx = withdrawal.transaction

            if tx.status != WalletTransaction.Status.PENDING:
                skipped_count += 1
                continue

            withdrawal.status = "success"
            withdrawal.save(update_fields=["status"])

            tx.status = WalletTransaction.Status.SUCCESS
            tx.save(update_fields=["status"])

            success_count += 1

    if success_count:
        modeladmin.message_user(request, f"{success_count} penarikan berhasil diperbarui.", messages.SUCCESS)

    if skipped_count:
        modeladmin.message_user(
            request,
            f"{skipped_count} penarikan dilewati karena statusnya "
            "sudah berubah atau tidak lagi diproses.",
            messages.WARNING,
        )

@admin.action(description="Tandai penarikan sebagai Gagal dan kembalikan saldo")
def mark_withdrawals_failed(modeladmin, request, queryset):
    failed_count = 0
    skipped_count = 0

    for withdrawal in queryset:
        with transaction.atomic():
            withdrawal = (WithdrawalRequest.objects.select_for_update().select_related("wallet", "transaction").get(pk=withdrawal.pk))

            if withdrawal.status != "processing":
                skipped_count += 1
                continue

            tx = withdrawal.transaction

            if tx.status != WalletTransaction.Status.PENDING:
                skipped_count += 1
                continue

            wallet = (Wallet.objects.select_for_update().get(pk=withdrawal.wallet_id))

            # Kembalikan saldo yang dipotong saat withdraw diajukan.
            wallet.balance += withdrawal.total_deduction
            wallet.total_withdrawn -= withdrawal.amount
            wallet.save(update_fields=["balance", "total_withdrawn", "updated_at"])

            withdrawal.status = "failed"
            withdrawal.save(update_fields=["status"])

            tx.status = WalletTransaction.Status.FAILED
            tx.save(update_fields=["status"])

            # Catat pengembalian dana
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type=WalletTransaction.Type.REFUND,
                status=WalletTransaction.Status.SUCCESS,
                amount=withdrawal.total_deduction,
                description="Pengembalian dana",
                reference=f"withdrawal_refund:{withdrawal.pk}",
                destination=tx.destination,
            )

            failed_count += 1

    if failed_count:
        modeladmin.message_user(
            request,
            f"{failed_count} penarikan ditandai gagal dan saldonya "
            "telah dikembalikan.",
            messages.SUCCESS,
        )

    if skipped_count:
        modeladmin.message_user(
            request,
            f"{skipped_count} penarikan dilewati karena statusnya "
            "sudah berubah atau tidak lagi diproses.",
            messages.WARNING,
        )

@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "wallet",
        "amount",
        "destination_type",
        "destination_name",
        "masked_account_number",
        "account_holder",
        "status",
        "created_at",
    )

    list_filter = ("status", "destination_type", "created_at")
    search_fields = (
        "wallet__user__username",
        "destination_name",
        "account_holder",
        "account_number",
    )
    readonly_fields = (
        "wallet",
        "transaction",
        "destination_type",
        "destination_name",
        "account_number",
        "account_holder",
        "amount",
        "created_at",
    )
    actions = (
        mark_withdrawals_success,
        mark_withdrawals_failed,
    )

    @admin.display(description="Nomor tujuan")
    def masked_account_number(self, obj):
        return f"••••{obj.account_number[-4:]}"

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "wallet",
        "transaction_type",
        "description",
        "amount",
        "status",
        "created_at",
    )
    list_filter = ("transaction_type", "status", "created_at")
    search_fields = ("wallet__user__username", "description", "reference")
    readonly_fields = (
        "wallet",
        "transaction_type",
        "status",
        "amount",
        "description",
        "reference",
        "destination",
        "created_at",
    )
    list_select_related = ("wallet",)

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "balance",
        "total_earned",
        "total_withdrawn",
        "total_donated",
        "updated_at",
    )
    search_fields = ("user__username", "user__email")
    readonly_fields = (
        "user",
        "balance",
        "total_earned",
        "total_withdrawn",
        "total_donated",
        "default_incentive",
        "updated_at",
    )

@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ("id", "wallet", "amount", "message", "created_at")
    search_fields = ("wallet__user__username", "message")
    readonly_fields = (
        "wallet",
        "transaction",
        "amount",
        "message",
        "created_at",
    )