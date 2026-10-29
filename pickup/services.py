from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from pickup.models import PickupRequest, PickupStatusHistory
from pickup.permissions import is_admin, is_collector

Status = PickupRequest.Status


class PickupServiceError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _log(pickup, previous_status, new_status, actor, note=""):
    PickupStatusHistory.objects.create(
        pickup=pickup,
        previous_status=previous_status,
        new_status=new_status,
        changed_by=actor,
        note=note,
    )


def _authorize(pickup, new_status, actor):
    if is_admin(actor):
        return
    if new_status == Status.CANCELLED:
        if pickup.giver_id == actor.pk:
            return
    elif new_status == Status.ASSIGNED:
        if is_collector(actor):
            return
    elif is_collector(actor) and pickup.collector_id == actor.pk:
        return
    raise PermissionDenied


@transaction.atomic
def create_pickup(pickup, giver):
    pickup.giver = giver
    pickup.status = Status.PENDING
    pickup.save()
    _log(pickup, "", Status.PENDING, giver)
    return pickup


@transaction.atomic
def change_status(pickup_id, new_status, actor, reason="", collector=None):
    pickup = get_object_or_404(PickupRequest.objects.select_for_update(), pk=pickup_id)

    _authorize(pickup, new_status, actor)

    if not pickup.can_transition_to(new_status):
        raise PickupServiceError(
            f"Status tidak dapat diubah dari {pickup.get_status_display()}.",
            status_code=409,
        )
    if new_status == Status.FAILED and not reason:
        raise PickupServiceError("Alasan kegagalan wajib diisi.")
    if new_status == Status.COMPLETED:
        items = list(pickup.items.all())
        if not items or any(item.actual_weight is None for item in items):
            raise PickupServiceError("Berat aktual semua barang harus diisi sebelum pickup diselesaikan.")

    previous_status = pickup.status
    now = timezone.now()

    if new_status == Status.ASSIGNED:
        if collector is None:
            raise PickupServiceError("Kurir wajib ditentukan.")
        pickup.collector = collector
        pickup.assigned_at = now
    elif new_status == Status.PENDING:
        pickup.collector = None
        pickup.assigned_at = None
    elif new_status == Status.COMPLETED:
        pickup.completed_at = now
    elif new_status == Status.CANCELLED:
        pickup.cancelled_at = now

    if new_status in (Status.CANCELLED, Status.FAILED):
        pickup.status_reason = reason

    pickup.status = new_status
    pickup.save()
    _log(pickup, previous_status, new_status, actor, reason)
    
    return pickup
