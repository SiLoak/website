"""Unified history of a giver's drop-offs (Submission) and pickups.

Both kinds are filtered in the database, then merged, sorted, and paginated
in Python. Weights are annotated in SQL and items are prefetched, so the
number of queries stays the same no matter how many entries a user has.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django import forms
from django.db.models import CharField, Count, Prefetch, Q, Sum
from django.db.models.functions import Cast
from django.urls import reverse
from django.utils import timezone

from pickup.models import PickupItem, PickupRequest
from waste.models import Submission, SubmissionItem

PickupStatus = PickupRequest.Status
SubmissionStatus = Submission.Status

ACTIVE, DONE, CANCELED = "active", "done", "canceled"
STATUS_GROUPS = {
    "dropoff": {
        ACTIVE: (SubmissionStatus.PENDING,),
        DONE: (SubmissionStatus.VERIFIED,),
        CANCELED: (SubmissionStatus.CANCELED,),
    },
    "pickup": {
        ACTIVE: (
            PickupStatus.PENDING, PickupStatus.ASSIGNED, PickupStatus.ON_THE_WAY,
            PickupStatus.ARRIVED, PickupStatus.WEIGHING,
        ),
        DONE: (PickupStatus.COMPLETED,),
        CANCELED: (PickupStatus.CANCELLED, PickupStatus.FAILED),
    },
}
SORT_KEYS = {
    "newest": (lambda entry: entry.created_at, True),
    "oldest": (lambda entry: entry.created_at, False),
    "heaviest": (lambda entry: entry.weight, True),
}
PAGE_SIZE = 10


class HistoryFilterForm(forms.Form):
    type = forms.ChoiceField(
        required=False,
        choices=(("", "Semua jenis"), ("dropoff", "Antar sendiri"), ("pickup", "Dijemput")),
    )
    status = forms.ChoiceField(
        required=False,
        choices=(("", "Semua status"), (ACTIVE, "Sedang diproses"), (DONE, "Selesai"), (CANCELED, "Dibatalkan / gagal")),
    )
    q = forms.CharField(required=False, max_length=80)
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    sort = forms.ChoiceField(
        required=False,
        choices=(("newest", "Terbaru"), ("oldest", "Terlama"), ("heaviest", "Terberat")),
    )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("date_from"), cleaned.get("date_to")
        if start and end and start > end:
            self.add_error("date_to", "Tanggal akhir harus setelah tanggal awal.")
        return cleaned

    def filters(self):
        """Valid filter values only; a bad field is ignored instead of failing the page."""
        self.is_valid()
        return {name: value for name, value in getattr(self, "cleaned_data", {}).items() if value}


@dataclass
class HistoryEntry:
    kind: str
    pk: object
    number: str
    created_at: datetime
    place: str
    waste_names: str
    weight: Decimal
    weight_is_actual: bool
    status: str
    status_display: str
    status_group: str
    cancellable: bool
    detail_url: str

    @property
    def select_value(self):
        return f"{self.kind}:{self.pk}"

    def __getitem__(self, key):
        return getattr(self, key)


def _status_group(kind, status):
    for group, statuses in STATUS_GROUPS[kind].items():
        if status in statuses:
            return group
    return ACTIVE


def _weight(obj):
    actual = obj.actual_weight
    if actual is not None:
        return actual, True
    return obj.total_weight or Decimal("0"), False


def _names(obj):
    return ", ".join(item.waste_type.name for item in obj.items.all())


def _dropoff_entry(submission):
    weight, is_actual = _weight(submission)
    return HistoryEntry(
        kind="dropoff",
        pk=submission.pk,
        number=f"#{submission.pk}",
        created_at=submission.created_at,
        place=submission.collection_point.name,
        waste_names=_names(submission),
        weight=weight,
        weight_is_actual=is_actual,
        status=submission.status,
        status_display=submission.get_status_display(),
        status_group=_status_group("dropoff", submission.status),
        cancellable=submission.status == SubmissionStatus.PENDING,
        detail_url=reverse("waste:detail", args=[submission.pk]),
    )


def _pickup_entry(pickup):
    weight, is_actual = _weight(pickup)
    return HistoryEntry(
        kind="pickup",
        pk=pickup.pk,
        number=f"#{str(pickup.pk)[:8]}",
        created_at=pickup.created_at,
        place=pickup.pickup_address or "Alamat penjemputan",
        waste_names=_names(pickup),
        weight=weight,
        weight_is_actual=is_actual,
        status=pickup.status,
        status_display=(
            "Selesai · menunggu verifikasi insentif"
            if pickup.status == PickupStatus.COMPLETED and pickup.verified_at is None
            else pickup.get_status_display()
        ),
        status_group=_status_group("pickup", pickup.status),
        cancellable=pickup.is_cancellable,
        detail_url=reverse("pickup:show_pickup_detail", args=[pickup.pk]),
    )


def _base_submissions(user):
    return (
        Submission.objects.filter(user=user)
        .select_related("collection_point")
        .annotate(total_weight=Sum("items__estimated_weight"))
        .prefetch_related(Prefetch("items", queryset=SubmissionItem.objects.select_related("waste_type")))
    )


def _base_pickups(user):
    return (
        PickupRequest.objects.filter(giver=user)
        .annotate(total_weight=Sum("items__estimated_weight"))
        .prefetch_related(Prefetch("items", queryset=PickupItem.objects.select_related("waste_type")))
    )


def _search_submissions(user, query):
    number = query.lstrip("#")
    condition = (
        Q(collection_point__name__icontains=query)
        | Q(collection_point__address__icontains=query)
        | Q(items__waste_type__name__icontains=query)
        | Q(items__waste_type__category__icontains=query)
    )
    if number.isdigit():
        condition |= Q(pk=int(number))
    # Filter through a subquery so the item join does not inflate the weight sum.
    return Submission.objects.filter(user=user).filter(condition).values("pk")


def _search_pickups(user, query):
    number = query.lstrip("#").replace("-", "").lower()
    condition = (
        Q(pickup_address__icontains=query)
        | Q(address_detail__icontains=query)
        | Q(items__waste_type__name__icontains=query)
        | Q(items__waste_type__category__icontains=query)
    )
    queryset = PickupRequest.objects.filter(giver=user)
    if len(number) >= 4 and all(char in "0123456789abcdef" for char in number):
        queryset = queryset.annotate(id_text=Cast("id", CharField()))
        condition |= Q(id_text__istartswith=number)
    return queryset.filter(condition).values("pk")


def build_history(user, filters):
    kind = filters.get("type")
    status_group = filters.get("status")
    query = filters.get("q", "").strip()
    entries = []

    if kind in (None, "dropoff"):
        submissions = _base_submissions(user)
        if status_group:
            submissions = submissions.filter(status__in=STATUS_GROUPS["dropoff"][status_group])
        if query:
            submissions = submissions.filter(pk__in=_search_submissions(user, query))
        if filters.get("date_from"):
            submissions = submissions.filter(created_at__date__gte=filters["date_from"])
        if filters.get("date_to"):
            submissions = submissions.filter(created_at__date__lte=filters["date_to"])
        entries.extend(_dropoff_entry(submission) for submission in submissions)

    if kind in (None, "pickup"):
        pickups = _base_pickups(user)
        if status_group:
            pickups = pickups.filter(status__in=STATUS_GROUPS["pickup"][status_group])
        if query:
            pickups = pickups.filter(pk__in=_search_pickups(user, query))
        if filters.get("date_from"):
            pickups = pickups.filter(created_at__date__gte=filters["date_from"])
        if filters.get("date_to"):
            pickups = pickups.filter(created_at__date__lte=filters["date_to"])
        entries.extend(_pickup_entry(pickup) for pickup in pickups)

    key, reverse_order = SORT_KEYS[filters.get("sort") or "newest"]
    entries.sort(key=key, reverse=reverse_order)
    return entries


def entry_for(user, kind, pk):
    """A single history entry owned by ``user``, or None."""
    if kind == "dropoff":
        obj = _base_submissions(user).filter(pk=pk).first()
        return _dropoff_entry(obj) if obj else None
    if kind == "pickup":
        obj = _base_pickups(user).filter(pk=pk).first()
        return _pickup_entry(obj) if obj else None
    return None


def history_stats(user):
    """Totals across all of the user's entries, computed with aggregate queries."""
    submissions = Submission.objects.filter(user=user).aggregate(
        total=Count("pk"),
        done=Count("pk", filter=Q(status=SubmissionStatus.VERIFIED)),
        active=Count("pk", filter=Q(status=SubmissionStatus.PENDING)),
    )
    pickups = PickupRequest.objects.filter(giver=user).aggregate(
        total=Count("pk"),
        done=Count("pk", filter=Q(status=PickupStatus.COMPLETED)),
        active=Count("pk", filter=Q(status__in=STATUS_GROUPS["pickup"][ACTIVE])),
    )
    dropoff_weight = SubmissionItem.objects.filter(
        submission__user=user, submission__status=SubmissionStatus.VERIFIED
    ).aggregate(total=Sum("actual_weight"))["total"] or Decimal("0")
    pickup_weight = PickupItem.objects.filter(
        pickup_request__giver=user, pickup_request__status=PickupStatus.COMPLETED
    ).aggregate(total=Sum("actual_weight"))["total"] or Decimal("0")
    return {
        "total": submissions["total"] + pickups["total"],
        "done": submissions["done"] + pickups["done"],
        "active": submissions["active"] + pickups["active"],
        "weight": dropoff_weight + pickup_weight,
    }


def parse_selection(values):
    """Split ``["dropoff:12", "pickup:<uuid>"]`` into submission ids and pickup ids."""
    dropoff_ids, pickup_ids = [], []
    for value in values:
        kind, _, raw_id = value.partition(":")
        if kind == "dropoff" and raw_id.isdigit():
            dropoff_ids.append(int(raw_id))
        elif kind == "pickup":
            try:
                pickup_ids.append(uuid.UUID(raw_id))
            except ValueError:
                continue
    return dropoff_ids, pickup_ids


def cancel_entries(user, dropoff_ids, pickup_ids, reason):
    """Cancel the user's own entries that can still be cancelled. Returns the count."""
    from pickup import services

    canceled = Submission.objects.filter(
        user=user, pk__in=dropoff_ids, status=SubmissionStatus.PENDING
    ).update(status=SubmissionStatus.CANCELED, canceled_at=timezone.now(), updated_at=timezone.now())

    pickups = PickupRequest.objects.filter(
        giver=user, pk__in=pickup_ids, status__in=PickupRequest.CANCELLABLE_STATUSES
    ).values_list("pk", flat=True)
    for pickup_id in list(pickups):
        services.change_status(pickup_id, PickupStatus.CANCELLED, user, reason=reason)
        canceled += 1
    return canceled
