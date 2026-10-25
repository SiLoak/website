from django.db import models
from django.core.validators import MinLengthValidator
from django.conf import settings
from django.db.models import Q

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
  scheduled_at = models.DateTimeField(
    help_text="Tanggal dan waktu pickup yang diminta oleh giver.",
  )

  # Request details
  item_description = models.TextField(
    blank=True,
    help_text="Deskripsi awal barang yang akan diambil.",
  )

  giver_note = models.TextField(
    blank=True,
    help_text="Catatan tambahan dari giver untuk collector.",
  )

  collector_note = models.TextField(
    blank=True,
    help_text="Catatan collector selama proses pickup.",
  )

  # Status
  status = models.CharField(
    max_length=20,
    choices=Status.choices,
    default=Status.PENDING,
    db_index=True,
  )

  status_reason = models.TextField(blank=True)

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
        fields=["scheduled_at", "status"],
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


class PickupStatusHistory(models.Model):
  """
  Audit trail for pickup status changes.
  """

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