from decimal import Decimal
from django import forms
from .models import Wallet

class WithdrawalForm(forms.Form):
    destination_type = forms.ChoiceField(label="Jenis tujuan", choices=[("bank","Rekening bank"),("ewallet","E-wallet")])
    destination_name = forms.CharField(label="Nama bank / e-wallet", max_length=80)
    account_number = forms.CharField(label="Nomor rekening / akun", max_length=40)
    account_holder = forms.CharField(label="Nama pemilik akun", max_length=100)
    amount = forms.DecimalField(label="Nominal penarikan", min_value=Decimal("10000"), max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={"min":"10000","step":"1000","placeholder":"Minimal Rp10.000"}))
    def __init__(self,*args,available_balance=Decimal("0"),**kwargs):
        super().__init__(*args,**kwargs); self.available_balance=available_balance
    def clean_amount(self):
        amount=self.cleaned_data["amount"]
        if amount>self.available_balance: raise forms.ValidationError("Nominal melebihi saldo tersedia.")
        return amount

class DonationForm(forms.Form):
    amount=forms.DecimalField(label="Nominal donasi",min_value=Decimal("1000"),max_digits=14,decimal_places=2,
        widget=forms.NumberInput(attrs={"min":"1000","step":"1000","placeholder":"Minimal Rp1.000"}))
    message=forms.CharField(label="Pesan (opsional)",required=False,max_length=180,widget=forms.Textarea(attrs={"rows":3}))
    def __init__(self,*args,available_balance=Decimal("0"),**kwargs):
        super().__init__(*args,**kwargs); self.available_balance=available_balance
    def clean_amount(self):
        amount=self.cleaned_data["amount"]
        if amount>self.available_balance: raise forms.ValidationError("Nominal donasi melebihi saldo tersedia.")
        return amount

class IncentivePreferenceForm(forms.Form):
    default_incentive=forms.ChoiceField(choices=Wallet._meta.get_field("default_incentive").choices)
