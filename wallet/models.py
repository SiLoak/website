from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="siloak_wallet")
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_earned = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_withdrawn = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_donated = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    default_incentive = models.CharField(max_length=10, choices=[("wallet","Terima insentif"),("donation","Donasikan")], default="wallet")
    updated_at = models.DateTimeField(auto_now=True)

class WalletTransaction(models.Model):
    class Type(models.TextChoices):
        EARNING = "earning", "Insentif masuk"
        WITHDRAWAL = "withdrawal", "Penarikan"
        DONATION = "donation", "Donasi"
        REFUND = "refund", "Pengembalian Dana"
    class Status(models.TextChoices):
        PENDING = "pending", "Diproses"
        SUCCESS = "success", "Berhasil"
        FAILED = "failed", "Gagal"
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=12, choices=Type.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUCCESS)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("1"))])
    description = models.CharField(max_length=180)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    destination = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at", "-pk"]

class WithdrawalRequest(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="withdrawals")
    transaction = models.OneToOneField(WalletTransaction, on_delete=models.PROTECT, related_name="withdrawal_request")
    destination_type = models.CharField(max_length=20, choices=[("bank","Rekening bank"),("ewallet","E-wallet")])
    destination_name = models.CharField(max_length=80)
    account_number = models.CharField(max_length=40)
    account_holder = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    transfer_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    service_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_deduction = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=12, choices=[("processing","Diproses"),("success","Berhasil"),("failed","Gagal")], default="processing")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at", "-pk"]

class Donation(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="donations")
    transaction = models.OneToOneField(WalletTransaction, on_delete=models.PROTECT, related_name="donation")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    message = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
