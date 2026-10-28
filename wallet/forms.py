from decimal import Decimal
from django import forms
from .models import Wallet

WITHDRAWAL_FIELD_CLASSES = (
    "w-full rounded-[0.6rem] border border-[#dbe2ee] bg-white "
    "px-[0.8rem] py-[0.7rem] text-[#142653] "
    "focus:border-[#2457D6] focus:outline focus:outline-2 "
    "focus:outline-[#2457D6]/20"
)

DONATION_FIELD_CLASSES = (
    "w-full rounded-[0.6rem] border border-[#dbe2ee] bg-white "
    "px-[0.8rem] py-[0.65rem] text-[#142653] "
    "focus:border-[#2457D6] focus:outline focus:outline-2 "
    "focus:outline-[#2457D6]/20"
)

class WithdrawalForm(forms.Form):
    BANK_CHOICES = [
        ("BCA", "BCA"),
        ("BNI", "BNI"),
        ("BRI", "BRI"),
        ("Mandiri", "Bank Mandiri"),
        ("BSI", "BSI"),
        ("CIMB Niaga", "CIMB Niaga"),
        ("BTN", "BTN"),
        ("Permata", "Bank Permata"),
        ("Danamon", "Bank Danamon"),
    ]

    EWALLET_CHOICES = [
        ("GoPay", "GoPay"),
        ("OVO", "OVO"),
        ("DANA", "DANA"),
        ("ShopeePay", "ShopeePay"),
        ("LinkAja", "LinkAja"),
    ]

    destination_type = forms.ChoiceField(
        label="Jenis Tujuan",
        choices=[
            ("bank", "Rekening Bank"),
            ("ewallet", "E-Wallet"),
        ],
        widget=forms.Select(attrs={"class": WITHDRAWAL_FIELD_CLASSES}),
    )

    destination_name = forms.ChoiceField(
        label="Bank / E-Wallet",
        choices=BANK_CHOICES,
        widget=forms.Select(attrs={"class": WITHDRAWAL_FIELD_CLASSES}),
    )

    account_number = forms.CharField(
        label="Nomor Rekening / Nomor HP",
        max_length=40,
        widget=forms.TextInput(attrs={
            "placeholder": "Masukkan nomor rekening atau HP",
            "autocomplete": "off",
            "class": WITHDRAWAL_FIELD_CLASSES,
        }),
    )

    account_holder = forms.CharField(
        label="Nama Pemilik Akun",
        max_length=100,
        widget=forms.TextInput(attrs={
            "placeholder": "Masukkan nama pemilik akun",
            "class": WITHDRAWAL_FIELD_CLASSES,
        }),
    )

    amount = forms.DecimalField(
        label="Nominal Penarikan",
        min_value=Decimal("10000"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "min": "10000",
            "step": "1000",
            "placeholder": "Minimal Rp10.000",
            "class": f"{WITHDRAWAL_FIELD_CLASSES} pl-10 text-m font-semibold",
        }),
    )

    def __init__(
        self, *args,
        available_balance=Decimal("0"),
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.available_balance = available_balance

        # Sesuaikan pilihan dropdown sebelum validasi form.
        selected_type = self.data.get(
            "destination_type",
            self.initial.get("destination_type", "bank")
        )

        if selected_type == "ewallet":
            self.fields["destination_name"].choices = (
                self.EWALLET_CHOICES
            )
        else:
            self.fields["destination_name"].choices = (
                self.BANK_CHOICES
            )

    def clean_amount(self):
        amount = self.cleaned_data["amount"]

        if amount < Decimal("10000"):
            raise forms.ValidationError(
                "Minimum penarikan adalah Rp10.000."
            )

        if amount > self.available_balance:
            raise forms.ValidationError(
                "Nominal melebihi saldo tersedia."
            )

        return amount

class DonationForm(forms.Form):
    amount = forms.DecimalField(
        label="Nominal donasi",
        min_value=Decimal("1000"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "min": "1000",
            "step": "1000",
            "placeholder": "Minimal Rp1.000",
            "class": f"{DONATION_FIELD_CLASSES} pl-10 text-m font-semibold",
        }),
    )
    message = forms.CharField(
        label="Pesan (opsional)",
        required=False,
        max_length=180,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "class": DONATION_FIELD_CLASSES,
        }),
    )

    def __init__(self, *args, available_balance=Decimal("0"), **kwargs):
        super().__init__(*args, **kwargs)
        self.available_balance = available_balance

    def clean_amount(self):
        amount=self.cleaned_data["amount"]
        if amount>self.available_balance: raise forms.ValidationError("Nominal donasi melebihi saldo tersedia.")
        return amount

class IncentivePreferenceForm(forms.Form):
    default_incentive=forms.ChoiceField(choices=Wallet._meta.get_field("default_incentive").choices)
