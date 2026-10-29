"""Numbers and activity for the staff monitor page (Pantau Aktivitas).

Every figure is an aggregate query and the feed is two capped queries, so
the page costs the same number of queries however busy the app is.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from pickup.models import PickupItem, PickupRequest, PickupStatusHistory
from wallet.models import WalletTransaction
from waste.models import Submission, SubmissionItem

PickupStatus = PickupRequest.Status
SubmissionStatus = Submission.Status

FEED_LIMIT = 20
STALE_PICKUP_HOURS = 24
STALE_DROPOFF_DAYS = 3
ACTIVE_PICKUP_STATUSES = (
    PickupStatus.ASSIGNED, PickupStatus.ON_THE_WAY, PickupStatus.ARRIVED, PickupStatus.WEIGHING,
)
FEED_KINDS = ("pickup", "dropoff")


def _name(user):
    if user is None:
        return "Sistem"
    return user.get_full_name() or user.get_username()


def summary():
    now = timezone.now()
    today = timezone.localdate()
    month_ago = now - timedelta(days=30)

    pickups = PickupRequest.objects.aggregate(
        waiting=Count("pk", filter=Q(status=PickupStatus.PENDING)),
        active=Count("pk", filter=Q(status__in=ACTIVE_PICKUP_STATUSES)),
        today=Count("pk", filter=Q(created_at__date=today)),
    )
    dropoffs = Submission.objects.aggregate(
        pending=Count("pk", filter=Q(status=SubmissionStatus.PENDING)),
        today=Count("pk", filter=Q(created_at__date=today)),
    )
    dropoff_weight = SubmissionItem.objects.filter(
        submission__status=SubmissionStatus.VERIFIED, submission__verified_at__gte=month_ago
    ).aggregate(total=Sum("actual_weight"))["total"] or Decimal("0")
    pickup_weight = PickupItem.objects.filter(
        pickup_request__status=PickupStatus.COMPLETED, pickup_request__completed_at__gte=month_ago
    ).aggregate(total=Sum("actual_weight"))["total"] or Decimal("0")
    incentive = WalletTransaction.objects.filter(
        transaction_type=WalletTransaction.Type.EARNING,
        status=WalletTransaction.Status.SUCCESS,
        created_at__gte=month_ago,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    return {
        "pickups_waiting": pickups["waiting"],
        "pickups_active": pickups["active"],
        "dropoffs_pending": dropoffs["pending"],
        "new_today": pickups["today"] + dropoffs["today"],
        "weight_30d": dropoff_weight + pickup_weight,
        "incentive_30d": incentive,
    }


def pickup_breakdown():
    counts = dict(PickupRequest.objects.values_list("status").annotate(count=Count("pk")))
    return [
        {"status": value, "label": label, "count": counts.get(value, 0)}
        for value, label in PickupStatus.choices
    ]


def attention():
    now = timezone.now()
    stale_pickups = (
        PickupRequest.objects.filter(
            status=PickupStatus.PENDING, created_at__lte=now - timedelta(hours=STALE_PICKUP_HOURS)
        )
        .select_related("giver")
        .order_by("created_at")[:10]
    )
    stale_dropoffs = (
        Submission.objects.filter(
            status=SubmissionStatus.PENDING, created_at__lte=now - timedelta(days=STALE_DROPOFF_DAYS)
        )
        .select_related("user", "collection_point")
        .order_by("created_at")[:10]
    )
    return {
        "pickups": [
            {
                "pk": pickup.pk,
                "label": f"Pickup #{str(pickup.pk)[:8]}",
                "who": _name(pickup.giver),
                "where": pickup.pickup_address,
                "since": pickup.created_at,
                "url": reverse("admin:pickup_pickuprequest_change", args=[pickup.pk]),
            }
            for pickup in stale_pickups
        ],
        "dropoffs": [
            {
                "pk": submission.pk,
                "label": f"Setoran #{submission.pk}",
                "who": _name(submission.user),
                "where": submission.collection_point.name,
                "since": submission.created_at,
                "url": reverse("admin:waste_submission_change", args=[submission.pk]),
            }
            for submission in stale_dropoffs
        ],
    }


def feed(kind=None):
    """Latest pickup status changes and setoran events, newest first."""
    events = []
    if kind in (None, "pickup"):
        history = PickupStatusHistory.objects.select_related("pickup", "changed_by").order_by("-created_at")[:FEED_LIMIT]
        events.extend(
            {
                "kind": "pickup",
                "pk": entry.pickup_id,
                "when": entry.created_at,
                "title": f"Pickup #{str(entry.pickup_id)[:8]} · {entry.get_new_status_display()}",
                "detail": entry.note or entry.pickup.pickup_address,
                "who": _name(entry.changed_by),
                "url": reverse("admin:pickup_pickuprequest_change", args=[entry.pickup_id]),
            }
            for entry in history
        )
    if kind in (None, "dropoff"):
        submissions = Submission.objects.select_related("user", "collection_point").order_by("-updated_at")[:FEED_LIMIT]
        events.extend(
            {
                "kind": "dropoff",
                "pk": submission.pk,
                "when": submission.updated_at,
                "title": f"Setoran #{submission.pk} · {submission.get_status_display()}",
                "detail": submission.collection_point.name,
                "who": _name(submission.user),
                "url": reverse("admin:waste_submission_change", args=[submission.pk]),
            }
            for submission in submissions
        )
    events.sort(key=lambda event: event["when"], reverse=True)
    return events[:FEED_LIMIT]
