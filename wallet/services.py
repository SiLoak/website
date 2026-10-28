from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Wallet, WalletTransaction

@transaction.atomic
def credit_wallet(user, amount, description, reference=""):
    # Panggil dari Waste Submission hanya setelah submission diverifikasi/selesai.
    amount=Decimal(str(amount))
    if amount<=0: raise ValidationError("Insentif harus lebih besar dari nol.")
    wallet=Wallet.objects.select_for_update().get_or_create(user=user)[0]
    if reference and WalletTransaction.objects.filter(wallet=wallet,transaction_type="earning",reference=reference).exists():
        return wallet, None
    wallet.balance+=amount; wallet.total_earned+=amount
    wallet.save(update_fields=["balance","total_earned","updated_at"])
    tx=WalletTransaction.objects.create(wallet=wallet,transaction_type="earning",status="success",amount=amount,description=description,reference=reference)
    return wallet,tx
