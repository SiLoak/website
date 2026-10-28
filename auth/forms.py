import re

from django import forms

from .models import UserProfile


class ProfileForm(forms.Form):
    first_name = forms.CharField(max_length=150, label="Nama depan")
    last_name = forms.CharField(max_length=150, required=False, label="Nama belakang")
    phone_number = forms.CharField(max_length=20, label="Nomor HP")

    def __init__(self, *args, user, **kwargs):
        self.user = user
        profile, _ = UserProfile.objects.get_or_create(user=user)
        self.profile = profile
        kwargs.setdefault("initial", {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": profile.phone_number,
        })
        super().__init__(*args, **kwargs)

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()
        digits = re.sub(r"\D", "", phone)
        if not re.fullmatch(r"[+0-9() .-]{8,20}", phone) or not 8 <= len(digits) <= 15:
            raise forms.ValidationError("Masukkan nomor HP yang valid.")
        return phone

    def save(self):
        self.user.first_name = self.cleaned_data["first_name"].strip()
        self.user.last_name = self.cleaned_data["last_name"].strip()
        self.user.save(update_fields=["first_name", "last_name"])
        self.profile.phone_number = self.cleaned_data["phone_number"]
        self.profile.save(update_fields=["phone_number"])
        return self.user


class PhoneOnboardingForm(forms.Form):
    phone_number = forms.CharField(max_length=20, label="Nomor HP")

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()
        digits = re.sub(r"\D", "", phone)
        if not re.fullmatch(r"[+0-9() .-]{8,20}", phone) or not 8 <= len(digits) <= 15:
            raise forms.ValidationError("Masukkan nomor HP yang valid.")
        return phone
