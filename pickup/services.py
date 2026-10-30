from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from pickup.models import PickupItem, PickupRequest, PickupStatusHistory
from pickup.permissions import is_admin, is_collector
from wallet.services import credit_wallet, record_donation
from waste.models import Submission

Status = PickupRequest.Status


class PickupServiceError(Exception):
    def __init__(self, message, status_code=400, code=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


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


@transaction.atomic
def verify_completed_pickup(pickup_id, verifier, note=""):
    pickup = get_object_or_404(
        PickupRequest.objects.select_for_update().select_related("giver"),
        pk=pickup_id,
    )

    if not is_admin(verifier) and not (
        is_collector(verifier) and pickup.collector_id == verifier.pk
    ):
        raise PermissionDenied
    if pickup.status != Status.COMPLETED:
        raise PickupServiceError(
            "Pickup harus diselesaikan sebelum insentif diproses.",
            code="not_completed",
        )
    if pickup.verified_at is not None:
        return pickup

    items = list(pickup.items.select_related("waste_type"))
    if not items or any(item.actual_weight is None for item in items):
        raise PickupServiceError(
            "Berat aktual semua barang harus diisi sebelum pickup diverifikasi.",
            code="missing_weight",
        )

    snapshot_updates = []
    for item in items:
        if item.unit_rate_snapshot is not None:
            continue
        if item.waste_type.rate_per_kg is None:
            raise PickupServiceError(
                "Tarif jenis sampah belum diatur sehingga insentif belum dapat diproses.",
                code="missing_rate",
            )
        item.unit_rate_snapshot = item.waste_type.rate_per_kg
        snapshot_updates.append(item)

    if snapshot_updates:
        PickupItem.objects.bulk_update(snapshot_updates, ["unit_rate_snapshot"])

    actual_reward = sum(
        (item.actual_weight * item.unit_rate_snapshot for item in items),
        Decimal("0"),
    )
    if actual_reward <= 0:
        raise PickupServiceError(
            "Total insentif harus lebih besar dari nol.",
            code="invalid_reward",
        )

    if pickup.incentive_allocation == Submission.IncentiveAllocation.WALLET:
        credit_wallet(
            user=pickup.giver,
            amount=actual_reward,
            description=f"Insentif pickup #{pickup.pk}",
            reference=f"pickup:{pickup.pk}",
        )
    else:
        record_donation(
            user=pickup.giver,
            amount=actual_reward,
            description=f"Donasi insentif pickup #{pickup.pk}",
            reference=f"pickup_donation:{pickup.pk}",
        )

    pickup.verified_at = timezone.now()
    pickup.verified_by = verifier
    pickup.save(update_fields=["verified_at", "verified_by", "updated_at"])
    _log(
        pickup,
        Status.COMPLETED,
        Status.COMPLETED,
        verifier,
        note or "Hasil timbang dan insentif diverifikasi petugas.",
    )
    return pickup
