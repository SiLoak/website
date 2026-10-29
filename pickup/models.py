import uuid

from django.db import models
from django.core.validators import MinLengthValidator
from django.conf import settings
from django.db.models import Q
from django.core.validators import MinValueValidator
from decimal import Decimal

from waste.models import Submission, WasteType

# Create your models here.
class PickupRequest(models.Model):
  """
  Represents a pickup request submitted by a giver.
  """

  class Status(models.TextChoices):
    PENDING = "PENDING", "Menunggu Penugasan"
    ASSIGNED = "ASSIGNED", "Kurir Ditugaskan"
    ON_THE_WAY = "ON_THE_WAY", "Kurir Dalam Perjalanan"
    ARRIVED = "ARRIVED", "Kurir Tiba"
    WEIGHING = "WEIGHING", "Penimbangan dan Verifikasi"
    COMPLETED = "COMPLETED", "Selesai"
    CANCELLED = "CANCELLED", "Dibatalkan"
    FAILED = "FAILED", "Gagal"

  class TimeSlot(models.TextChoices):
    S0810 = "08:00-10:00", "08.00 - 10.00"
    S1012 = "10:00-12:00", "10.00 - 12.00"
    S1214 = "12:00-14:00", "12.00 - 14.00"
    S1416 = "14:00-16:00", "14.00 - 16.00"
    S1618 = "16:00-18:00", "16.00 - 18.00"

  CANCELLABLE_STATUSES = (Status.PENDING, Status.ASSIGNED)

  ALLOWED_TRANSITIONS = {
    Status.PENDING: (Status.ASSIGNED, Status.CANCELLED),
    Status.ASSIGNED: (Status.PENDING, Status.ON_THE_WAY, Status.CANCELLED),
    Status.ON_THE_WAY: (Status.ARRIVED, Status.FAILED),
    Status.ARRIVED: (Status.WEIGHING, Status.FAILED),
    Status.WEIGHING: (Status.COMPLETED, Status.FAILED),
    Status.COMPLETED: (),
    Status.CANCELLED: (),
    Status.FAILED: (),
  }

  # Primary key
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

  # User relationships
  giver = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.PROTECT,
    related_name="pickup_requests",
  )

  collector = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name="assigned_pickups",
  )

  # Pickup address (snapshot)
  pickup_address = models.TextField(
    validators=[MinLengthValidator(5)],
    help_text="Alamat lengkap lokasi pengambilan barang.",
  )

  address_detail = models.CharField(
    max_length=255,
    blank=True,
    help_text="Detail alamat, seperti nomor rumah atau patokan.",
  )

  latitude = models.DecimalField(
    max_digits=10,
    decimal_places=7,
    null=True,
    blank=True,
  )

  longitude = models.DecimalField(
    max_digits=10,
    decimal_places=7,
    null=True,
    blank=True,
  )

  # Contact phone
  contact_phone = models.CharField(
    max_length=20,
    blank=True
  )

  # Schedule
  scheduled_date = models.DateField(
    help_text="Tanggal pickup yang diminta oleh giver.",
  )

  time_slot = models.CharField(
    max_length=11,
    choices=TimeSlot.choices,
  )

  # Status
  status = models.CharField(
    max_length=20,
    choices=Status.choices,
    default=Status.PENDING,
    db_index=True,
  )

  status_reason = models.TextField(blank=True)

  # Incentive
  incentive_allocation = models.CharField(
    max_length=12,
    choices=Submission.IncentiveAllocation.choices, default=Submission.IncentiveAllocation.WALLET,
  )

  # Timestamps
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  assigned_at = models.DateTimeField(null=True, blank=True)
  completed_at = models.DateTimeField(null=True, blank=True)
  cancelled_at = models.DateTimeField(null=True, blank=True)

  class Meta:
    ordering = ["-created_at"]
    indexes = [
      models.Index(
        fields=["giver", "-created_at"],
        name="pickup_giver_date_idx",
      ),
      models.Index(
        fields=["collector", "status"],
        name="pickup_collector_status_idx",
      ),
      models.Index(
        fields=["scheduled_date", "status"],
        name="pickup_schedule_status_idx",
      ),
    ]
    constraints = [
      models.CheckConstraint(
        check=Q(status__in=["PENDING", "CANCELLED", "FAILED"]) | Q(collector__isnull=False),
        name="pickup_active_requires_collector",
      ),
      models.CheckConstraint(
        check=Q(latitude__isnull=True, longitude__isnull=True) | Q(latitude__isnull=False, longitude__isnull=False),
        name="pickup_coordinates_both_or_none",
      )
    ]

  def __str__(self):
    return f"Pickup #{self.pk} - {self.get_status_display()}"

  def can_transition_to(self, new_status):
    return new_status in self.ALLOWED_TRANSITIONS.get(self.status, ())

  @property
  def is_cancellable(self):
    return self.status in self.CANCELLABLE_STATUSES

  @property
  def estimated_weight(self):
    return sum(
      (item.estimated_weight for item in self.items.all()), Decimal("0")
    )

  @property
  def actual_weight(self):
    items = list(self.items.all())
    if not items or any(item.actual_weight is None for item in items):
      return None
    return sum((item.actual_weight for item in items), Decimal("0"))

  @property
  def estimated_reward(self):
    items = list(self.items.all())
    if any(item.unit_rate_snapshot is None for item in items):
      return None
    return sum((item.estimated_subtotal for item in items), Decimal("0"))

  @property
  def actual_reward(self):
    items = list(self.items.all())
    if not items or any(
      item.actual_weight is None or item.unit_rate_snapshot is None
      for item in items
    ):
      return None
    return sum((item.actual_subtotal for item in items), Decimal("0"))


class PickupItem(models.Model):
  """
  Represents pickup items.
  """

  pickup_request = models.ForeignKey(
    PickupRequest,
    on_delete=models.CASCADE,
    related_name="items",
  )

  waste_type = models.ForeignKey(
    WasteType,
    on_delete=models.PROTECT,
    related_name="pickup_items",
  )

  estimated_weight = models.DecimalField(
    max_digits=8,
    decimal_places=2,
    validators=[MinValueValidator(Decimal("0.01"))],
  )

  actual_weight = models.DecimalField(
    max_digits=8,
    decimal_places=2,
    null=True,
    blank=True,
    validators=[MinValueValidator(Decimal("0.01"))],
  )

  unit_rate_snapshot = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    null=True,
    blank=True,
  )

  class Meta:
    ordering = ["pk"]
    constraints = [
      models.UniqueConstraint(
        fields=["pickup_request", "waste_type"],
        name="unique_waste_type_per_pickup_request",
      )
    ]

  def __str__(self):
    return f"{self.waste_type} — {self.submission}"

  @property
  def estimated_subtotal(self):
    if self.unit_rate_snapshot is None:
      return None
    return self.estimated_weight * self.unit_rate_snapshot

  @property
  def actual_subtotal(self):
    if self.actual_weight is None or self.unit_rate_snapshot is None:
      return None
    return self.actual_weight * self.unit_rate_snapshot


class PickupStatusHistory(models.Model):
  """
  Audit trail for pickup status changes.
  """

  # Primary key
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

  # Pickup request relationships
  pickup = models.ForeignKey(
    PickupRequest,
    on_delete=models.CASCADE,
    related_name="status_history",
  )

  # Prev and new status
  previous_status = models.CharField(
    max_length=20,
    choices=PickupRequest.Status.choices,
    blank=True,
  )

  new_status = models.CharField(
    max_length=20,
    choices=PickupRequest.Status.choices,
  )

  # Who changed the status
  changed_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="pickup_status_changes",
  )

  # Note
  note = models.TextField(blank=True)

  # Timestamps
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ["created_at"]
    indexes = [
      models.Index(
        fields=["pickup", "created_at"],
        name="pickup_history_date_idx",
      )
    ]

  def __str__(self):
    return f"Pickup #{self.pickup_id}: {self.previous_status or 'INITIAL'} -> {self.new_status}"