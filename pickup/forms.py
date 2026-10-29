import re
from datetime import datetime, timedelta
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import inlineformset_factory, modelformset_factory
from django.utils import timezone

from waste.forms import BaseSubmissionItemFormSet, WasteTypeChoiceField
from waste.models import Submission, WasteType

from pickup.models import PickupRequest, PickupItem

INPUT_CLASS = (
  "w-full rounded-lg border border-border-slate bg-surface-card px-3 py-3 "
  "text-text-primary focus:bg-surface-card focus:outline-none "
  "focus:ring-2 focus:ring-primary-container/20"
)

MAX_ADVANCE_DAYS = 30
PHONE_PATTERN = re.compile(r"^(?:\+62|62|0)(8\d{8,11})$")

class PickupRequestForm(forms.ModelForm):
  DATE_TODAY = "today"
  DATE_TOMORROW = "tomorrow"
  DATE_DAY_AFTER = "day_after"
  DATE_CUSTOM = "custom"
  DATE_OFFSETS = {
    DATE_TODAY: 0,
    DATE_TOMORROW: 1,
    DATE_DAY_AFTER: 2,
  }

  delivery_method = forms.ChoiceField(
    choices=(("minta_dijemput", "Minta dijemput"),),
    required=False,
    label="Cara menyetor",
  )

  pickup_date_option = forms.ChoiceField(
    choices=(
      (DATE_TODAY, "Hari ini"),
      (DATE_TOMORROW, "Besok"),
      (DATE_DAY_AFTER, "Lusa"),
      (DATE_CUSTOM, "Pilih tanggal lain"),
    ),
    initial=DATE_TODAY,
    widget=forms.RadioSelect,
    label="Pilih tanggal",
  )

  custom_date = forms.DateField(
    required=False,
    label="Tanggal lain",
    widget=forms.DateInput(
      attrs={"class": "waste-address-control", "type": "date"},
      format="%Y-%m-%d",
    ),
  )

  time_slot = forms.ChoiceField(
    choices=PickupRequest.TimeSlot.choices,
    widget=forms.RadioSelect,
    label="Pilih rentang waktu",
    error_messages={"required": "Pilih rentang waktu penjemputan."},
  )

  latitude = forms.DecimalField(required=False, widget=forms.HiddenInput)
  longitude = forms.DecimalField(required=False, widget=forms.HiddenInput)

  incentive_allocation = forms.ChoiceField(
    choices=Submission.IncentiveAllocation.choices,
    required=False,
    initial=Submission.IncentiveAllocation.WALLET,
    label="Insentifmu",
  )

  class Meta:
    model = PickupRequest
    fields = [
      "address_detail",
      "contact_phone",
      "latitude",
      "longitude",
      "time_slot",
      "incentive_allocation",
    ]
    labels = {
      "address_detail": "Detail alamat & patokan",
      "contact_phone": "Nomor HP yang bisa dihubungi",
      "incentive_allocation": "Insentifmu",
    }
    widgets = {
      "address_detail": forms.Textarea(
        attrs={
          "class": "waste-address-control",
          "rows": 3,
          "placeholder": "Contoh: Jl. Mawar No. 12, RT 03/RW 05, pagar hijau di samping warung",
        }
      ),
      "contact_phone": forms.TextInput(
        attrs={
          "class": "waste-address-control",
          "type": "tel",
          "inputmode": "tel",
          "placeholder": "Contoh: 081234567890",
        }
      ),
    }

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    today = timezone.localdate()
    self.fields["custom_date"].widget.attrs.update(
      {
        "min": today.isoformat(),
        "max": (today + timedelta(days=MAX_ADVANCE_DAYS)).isoformat(),
      }
    )

  def clean_delivery_method(self):
    return self.cleaned_data.get("delivery_method") or "minta_dijemput"

  def clean_incentive_allocation(self):
    return self.cleaned_data.get("incentive_allocation") or Submission.IncentiveAllocation.WALLET

  def clean_address_detail(self):
    address = (self.cleaned_data.get("address_detail") or "").strip()
    if len(address) < 10:
      raise ValidationError(
        "Tulis alamat selengkapnya agar kurir mudah menemukan lokasi Anda."
      )
    return address

  def clean_contact_phone(self):
    raw = self.cleaned_data.get("contact_phone") or ""
    phone = re.sub(r"[\s\-().]", "", raw)
    match = PHONE_PATTERN.match(phone)
    if not match:
      raise ValidationError(
        "Masukkan nomor HP yang valid, misalnya 081234567890."
      )
    return "0" + match.group(1)

  def _clean_coordinate(self, name, limit):
    value = self.cleaned_data.get(name)
    if value is None:
      return None
    if abs(value) > limit:
      raise ValidationError("Koordinat lokasi tidak valid.")
    return value.quantize(Decimal("0.000001"))

  def clean_latitude(self):
    return self._clean_coordinate("latitude", Decimal("90"))

  def clean_longitude(self):
    return self._clean_coordinate("longitude", Decimal("180"))

  def clean(self):
    cleaned_data = super().clean()
    option = cleaned_data.get("pickup_date_option")
    today = timezone.localdate()
    scheduled_date = None

    if option in self.DATE_OFFSETS:
      scheduled_date = today + timedelta(days=self.DATE_OFFSETS[option])
    elif option == self.DATE_CUSTOM:
      custom_date = cleaned_data.get("custom_date")
      if custom_date is None:
        if "custom_date" not in self.errors:
          self.add_error("custom_date", "Pilih tanggal penjemputan.")
      elif custom_date < today:
        self.add_error("custom_date", "Tanggal tidak boleh sudah lewat.")
      elif custom_date > today + timedelta(days=MAX_ADVANCE_DAYS):
        self.add_error("custom_date", f"Penjemputan maksimal {MAX_ADVANCE_DAYS} hari ke depan.")
      else:
        scheduled_date = custom_date

    time_slot = cleaned_data.get("time_slot")
    if scheduled_date == today and time_slot:
      slot_start = datetime.strptime(time_slot.split("-")[0], "%H:%M").time()
      if slot_start <= timezone.localtime().time():
        self.add_error("time_slot", "Rentang waktu ini sudah lewat. Pilih rentang waktu lain atau tanggal lain.")

    if "latitude" in cleaned_data and "longitude" in cleaned_data:
      if (cleaned_data["latitude"] is None) != (cleaned_data["longitude"] is None):
        self.add_error(None, "Titik lokasi di peta belum lengkap. Pilih ulang lokasi penjemputan.")

    cleaned_data["scheduled_date"] = scheduled_date
    return cleaned_data

  def save(self, commit=True):
    self.instance.scheduled_date = self.cleaned_data["scheduled_date"]
    return super().save(commit=commit)

class PickupItemForm(forms.ModelForm):
  waste_type = WasteTypeChoiceField(
    queryset=WasteType.objects.none(),
    label="Jenis sampah",
    widget=forms.Select(attrs={"class": INPUT_CLASS}),
  )

  class Meta:
    model = PickupItem
    fields = [
      "waste_type",
      "estimated_weight",
    ]
    widgets = {
      "estimated_weight": forms.NumberInput(
        attrs={
          "class": INPUT_CLASS,
          "min": "0.01",
          "step": "0.01",
          "placeholder": "Contoh: 2.50",
        }
      ),
    }

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    waste_types = WasteType.objects.filter(is_active=True)
    if self.instance and self.instance.pk:
      waste_types = WasteType.objects.filter(
        Q(is_active=True) | Q(pk=self.instance.waste_type_id)
      )
    self.fields["waste_type"].queryset = waste_types.distinct()


class BasePickupItemFormSet(BaseSubmissionItemFormSet):
  @classmethod
  def get_default_prefix(cls):
    return "items"


PickupItemFormSet = inlineformset_factory(
  PickupRequest,
  PickupItem,
  form=PickupItemForm,
  formset=BasePickupItemFormSet,
  extra=1,
  min_num=1,
  max_num=6,
  validate_min=True,
  validate_max=True,
  can_delete=True,
)


class PickupItemWeighingForm(forms.ModelForm):
  class Meta:
    model = PickupItem
    fields = ["actual_weight"]
    widgets = {
      "actual_weight": forms.NumberInput(
        attrs={
          "class": INPUT_CLASS,
          "min": "0.01",
          "step": "0.01",
          "placeholder": "Contoh: 2.50",
        }
      ),
    }

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields["actual_weight"].required = True


PickupWeighingFormSet = modelformset_factory(
  PickupItem,
  form=PickupItemWeighingForm,
  extra=0,
)