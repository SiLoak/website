from django.utils.html import strip_tags
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from datetime import time, timedelta
from decimal import Decimal

from pickup.models import PickupRequest, PickupItem, PickupStatusHistory
from pickup.permissions import is_admin
from pickup.services import PickupServiceError, create_pickup


MAX_DAYS_AHEAD = 30

PROGRESS_STATUSES = (
  PickupRequest.Status.PENDING,
  PickupRequest.Status.ON_THE_WAY,
  PickupRequest.Status.ARRIVED,
  PickupRequest.Status.WEIGHING,
  PickupRequest.Status.FAILED,
)


def _display_name(user):
  if user is None:
    return None
  return user.get_full_name() or user.get_username()


def _current_unit_rate(waste_type):
  return getattr(waste_type, "rate_per_kg", None)


# =============== READ SERIALIZERS ===============

class PickupItemSerializer(serializers.ModelSerializer):
  waste_type_name = serializers.StringRelatedField(
    source="waste_type", read_only=True
  )
  estimated_subtotal = serializers.DecimalField(
    max_digits=14, decimal_places=2, read_only=True
  )
  actual_subtotal = serializers.DecimalField(
    max_digits=14, decimal_places=2, read_only=True
  )

  class Meta:
    model = PickupItem
    fields = [
      "id", "waste_type", "waste_type_name",
      "estimated_weight", "actual_weight", "unit_rate_snapshot",
      "estimated_subtotal", "actual_subtotal",
    ]
    read_only_fields = ["id", "actual_weight", "unit_rate_snapshot"]


class PickupStatusHistorySerializer(serializers.ModelSerializer):
  previous_status_display = serializers.SerializerMethodField()
  new_status_display = serializers.CharField(
    source="get_new_status_display", read_only=True
  )
  changed_by_name = serializers.SerializerMethodField()

  class Meta:
    model = PickupStatusHistory
    fields = [
      "id", "previous_status", "previous_status_display",
      "new_status", "new_status_display",
      "changed_by", "changed_by_name", "note", "created_at",
    ]
    read_only_fields = fields

  def get_previous_status_display(self, obj):
    return obj.get_previous_status_display() if obj.previous_status else ""

  def get_changed_by_name(self, obj):
    return _display_name(obj.changed_by)


class PickupRequestSerializer(serializers.ModelSerializer):
  giver_name = serializers.SerializerMethodField()
  collector_name = serializers.SerializerMethodField()
  verified_by_name = serializers.SerializerMethodField()
  contact_phone = serializers.SerializerMethodField()

  status_display = serializers.CharField(
    source="get_status_display", read_only=True
  )
  time_slot_display = serializers.CharField(
    source="get_time_slot_display", read_only=True
  )
  incentive_allocation_display = serializers.CharField(
    source="get_incentive_allocation_display", read_only=True
  )

  items = PickupItemSerializer(many=True, read_only=True)
  status_history = PickupStatusHistorySerializer(many=True, read_only=True)

  estimated_weight = serializers.DecimalField(
    max_digits=12, decimal_places=2, read_only=True
  )
  actual_weight = serializers.DecimalField(
    max_digits=12, decimal_places=2, read_only=True
  )
  estimated_reward = serializers.DecimalField(
    max_digits=14, decimal_places=2, read_only=True
  )
  actual_reward = serializers.DecimalField(
    max_digits=14, decimal_places=2, read_only=True
  )

  is_cancellable = serializers.SerializerMethodField()
  allowed_next_statuses = serializers.SerializerMethodField()

  class Meta:
    model = PickupRequest
    fields = [
      "id",
      "giver", "giver_name",
      "collector", "collector_name",
      "pickup_address", "address_detail", "latitude", "longitude",
      "contact_phone",
      "scheduled_date", "time_slot", "time_slot_display",
      "status", "status_display", "status_reason",
      "incentive_allocation", "incentive_allocation_display",
      "items",
      "estimated_weight", "actual_weight",
      "estimated_reward", "actual_reward",
      "is_cancellable",
      "allowed_next_statuses",
      "created_at", "updated_at", "assigned_at", "completed_at",
      "cancelled_at", "verified_at", "verified_by", "verified_by_name",
      "status_history",
    ]
    read_only_fields = fields

  def get_allowed_next_statuses(self, obj):
    return [
      status.value
      for status in PickupRequest.ALLOWED_TRANSITIONS.get(obj.status, ())
    ]

  def _viewer_roles(self, obj):
    user = self.context["request"].user
    return obj.giver_id == user.pk, obj.collector_id == user.pk, is_admin(user)

  def get_giver_name(self, obj):
    return _display_name(obj.giver)

  def get_collector_name(self, obj):
    return _display_name(obj.collector)

  def get_verified_by_name(self, obj):
    return _display_name(obj.verified_by)

  def get_contact_phone(self, obj):
    is_owner, is_assigned, user_is_admin = self._viewer_roles(obj)
    if is_owner or is_assigned or user_is_admin:
      return obj.contact_phone
    return None

  def get_is_cancellable(self, obj):
    is_owner, _, user_is_admin = self._viewer_roles(obj)
    return obj.is_cancellable and (is_owner or user_is_admin)


class PickupRequestListSerializer(serializers.ModelSerializer):
  status_display = serializers.CharField(
    source="get_status_display", read_only=True
  )
  time_slot_display = serializers.CharField(
    source="get_time_slot_display", read_only=True
  )
  giver_name = serializers.SerializerMethodField()
  collector_name = serializers.SerializerMethodField()
  item_names = serializers.SerializerMethodField()
  estimated_weight = serializers.DecimalField(
    max_digits=12, decimal_places=2, read_only=True
  )
  actual_weight = serializers.DecimalField(
    max_digits=12, decimal_places=2, read_only=True
  )
  estimated_reward = serializers.DecimalField(
    max_digits=14, decimal_places=2, read_only=True
  )

  class Meta:
    model = PickupRequest
    fields = [
      "id", "pickup_address", "address_detail",
      "scheduled_date", "time_slot", "time_slot_display",
      "status", "status_display",
      "giver_name", "collector_name", "item_names",
      "estimated_weight", "actual_weight", "estimated_reward",
      "created_at", "completed_at",
    ]
    read_only_fields = fields

  def get_giver_name(self, obj):
    return _display_name(obj.giver)

  def get_collector_name(self, obj):
    return _display_name(obj.collector)

  def get_item_names(self, obj):
    return [str(item.waste_type) for item in obj.items.all()]


# =============== WRITE SERIALIZERS ===============

class PickupRequestCreateSerializer(serializers.ModelSerializer):
  items = PickupItemSerializer(many=True, allow_empty=False)

  class Meta:
    model = PickupRequest
    fields = [
      "pickup_address", "address_detail", "latitude", "longitude",
      "contact_phone", "scheduled_date", "time_slot",
      "incentive_allocation", "items",
    ]

  def validate_pickup_address(self, value):
    value = strip_tags(value).strip()
    if len(value) < 5:
      raise serializers.ValidationError("Alamat minimal 5 karakter.")
    return value

  def validate_address_detail(self, value):
    return strip_tags(value).strip()

  def validate_contact_phone(self, value):
    return strip_tags(value).strip()

  def validate_scheduled_date(self, value):
    today = timezone.localdate()
    if value < today:
      raise serializers.ValidationError("Tanggal pickup tidak boleh di masa lalu.")
    if value > today + timedelta(days=MAX_DAYS_AHEAD):
      raise serializers.ValidationError(
        f"Tanggal pickup maksimal {MAX_DAYS_AHEAD} hari ke depan."
      )
    return value

  def validate_items(self, items):
    waste_type_ids = [item["waste_type"].pk for item in items]
    if len(waste_type_ids) != len(set(waste_type_ids)):
      raise serializers.ValidationError(
        "Satu jenis sampah hanya boleh muncul sekali dalam satu permintaan."
      )
    return items

  def validate(self, attrs):
    latitude = attrs.get("latitude")
    longitude = attrs.get("longitude")
    if (latitude is None) != (longitude is None):
      raise serializers.ValidationError(
        {"latitude": "Latitude dan longitude harus diisi bersamaan."}
      )

    if attrs["scheduled_date"] == timezone.localdate():
      end_hour, end_minute = map(int, attrs["time_slot"].split("-")[1].split(":"))
      if timezone.localtime().time() >= time(end_hour, end_minute):
        raise serializers.ValidationError(
          {"time_slot": "Slot waktu ini sudah lewat. Pilih slot lain."}
        )

    return attrs

  def create(self, validated_data):
    items_data = validated_data.pop("items")
    user = self.context["request"].user

    with transaction.atomic():
      pickup = PickupRequest(giver=user, **validated_data)
      try:
        pickup = create_pickup(pickup, user)
      except PickupServiceError as exc:
        raise serializers.ValidationError(exc.message)

      PickupItem.objects.bulk_create([
        PickupItem(
          pickup_request=pickup,
          waste_type=item["waste_type"],
          estimated_weight=item["estimated_weight"],
          unit_rate_snapshot=_current_unit_rate(item["waste_type"]),
        )
        for item in items_data
      ])

    return pickup

  def to_representation(self, instance):
    return PickupRequestSerializer(instance, context=self.context).data


class PickupStatusUpdateSerializer(serializers.Serializer):
  status = serializers.ChoiceField(
    choices=[(s.value, s.label) for s in PROGRESS_STATUSES]
  )
  note = serializers.CharField(
    required=False, allow_blank=True, max_length=500, default=""
  )

  def validate_note(self, value):
    return strip_tags(value).strip()

  def validate(self, attrs):
    pickup = self.context["pickup"]
    new_status = attrs["status"]

    if not pickup.can_transition_to(new_status):
      raise serializers.ValidationError({
        "status": (
          f"Status tidak dapat diubah dari "
          f"'{pickup.get_status_display()}' ke "
          f"'{PickupRequest.Status(new_status).label}'."
        )
      })

    if new_status == PickupRequest.Status.FAILED and not attrs["note"]:
      raise serializers.ValidationError(
        {"note": "Alasan wajib diisi jika pickup gagal."}
      )

    return attrs


class PickupCancelSerializer(serializers.Serializer):
  reason = serializers.CharField(
    required=False, allow_blank=True, max_length=500, default=""
  )

  def validate_reason(self, value):
    return strip_tags(value).strip()

  def validate(self, attrs):
    pickup = self.context["pickup"]
    if not pickup.is_cancellable:
      raise serializers.ValidationError(
        "Pickup ini sudah tidak dapat dibatalkan."
      )
    return attrs


class PickupWeighingItemSerializer(serializers.Serializer):
  id = serializers.IntegerField()
  actual_weight = serializers.DecimalField(
    max_digits=8, decimal_places=2, min_value=Decimal("0.01")
  )


class PickupWeighingSerializer(serializers.Serializer):
  items = PickupWeighingItemSerializer(many=True, allow_empty=False)

  def validate(self, attrs):
    pickup = self.context["pickup"]

    if pickup.status != PickupRequest.Status.WEIGHING:
      raise serializers.ValidationError(
        "Penimbangan hanya dapat dilakukan pada tahap Penimbangan dan Verifikasi."
      )

    given_ids = [item["id"] for item in attrs["items"]]
    if len(given_ids) != len(set(given_ids)):
      raise serializers.ValidationError("Terdapat item yang dikirim lebih dari sekali.")

    expected_ids = set(pickup.items.values_list("pk", flat=True))
    if set(given_ids) != expected_ids:
      raise serializers.ValidationError(
        "Berat aktual harus diisi untuk semua item pada pickup ini."
      )

    return attrs

  @transaction.atomic
  def save(self, **kwargs):
    pickup = self.context["pickup"]
    weights = {
      item["id"]: item["actual_weight"]
      for item in self.validated_data["items"]
    }

    items = list(PickupItem.objects.filter(pickup_request=pickup))
    for item in items:
      item.actual_weight = weights[item.pk]
    PickupItem.objects.bulk_update(items, ["actual_weight"])

    return pickup