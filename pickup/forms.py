from django.forms import ModelForm, ValidationError
from django.utils import timezone

from pickup.models import PickupRequest

class PickupForm(ModelForm):
  class Meta:
    model = PickupRequest
    fields = [
      "pickup_address",
      "address_detail",
      "latitude",
      "longitude",
      "contact_phone",
      "scheduled_at",
      "item_description",
      "giver_note",
    ]

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields["scheduled_at"].input_formats = ["%Y-%m-%dT%H:%M"]

  def clean_scheduled_at(self):
    value = self.cleaned_data["scheduled_at"]
    if value <= timezone.now():
      raise ValidationError("Jadwal pickup harus di masa depan.")
    return value