from decimal import Decimal

from django.urls import reverse

from pickup.models import PickupRequest
from waste.models import Submission


def build_history_context(user):
    submissions = list(
        Submission.objects.filter(user=user)
        .select_related("collection_point")
        .prefetch_related("items__waste_type")
    )
    pickups = list(
        PickupRequest.objects.filter(giver=user)
        .prefetch_related("items__waste_type")
    )

    activity = []
    verified_submissions = [
        submission
        for submission in submissions
        if submission.status == Submission.Status.VERIFIED
    ]
    verified_pickups = [pickup for pickup in pickups if pickup.verified_at is not None]
    weighed_pickups = [
        pickup for pickup in pickups if pickup.status == PickupRequest.Status.COMPLETED
    ]

    for submission in submissions:
        is_verified = submission.status == Submission.Status.VERIFIED
        activity.append(
            {
                "kind": "submission",
                "kind_label": "Antar sendiri",
                "reference": str(submission.pk),
                "date": submission.created_at,
                "location": submission.collection_point.name,
                "items": [item.waste_type.name for item in submission.items.all()],
                "weight_label": "Aktual" if is_verified and submission.actual_weight is not None else "Estimasi",
                "weight": submission.actual_weight if is_verified and submission.actual_weight is not None else submission.estimated_weight,
                "status": submission.get_status_display(),
                "status_class": "success" if is_verified else "danger" if submission.status == Submission.Status.CANCELED else "pending",
                "url": reverse("waste:detail", kwargs={"submission_id": submission.pk}),
            }
        )

    for pickup in pickups:
        is_completed = pickup.status == PickupRequest.Status.COMPLETED
        status = pickup.get_status_display()
        if is_completed and pickup.verified_at is None:
            status = "Selesai · menunggu verifikasi insentif"
        activity.append(
            {
                "kind": "pickup",
                "kind_label": "Minta dijemput",
                "reference": str(pickup.pk)[:8],
                "date": pickup.created_at,
                "location": pickup.pickup_address,
                "items": [item.waste_type.name for item in pickup.items.all()],
                "weight_label": "Aktual" if is_completed and pickup.actual_weight is not None else "Estimasi",
                "weight": pickup.actual_weight if is_completed and pickup.actual_weight is not None else pickup.estimated_weight,
                "status": status,
                "status_class": "success" if is_completed and pickup.verified_at else "danger" if pickup.status in (PickupRequest.Status.CANCELLED, PickupRequest.Status.FAILED) else "pending",
                "url": reverse("pickup:show_pickup_detail", kwargs={"pickup_id": pickup.pk}),
            }
        )

    activity.sort(key=lambda row: row["date"], reverse=True)

    total_actual_weight = sum(
        (submission.actual_weight or Decimal("0") for submission in verified_submissions),
        Decimal("0"),
    ) + sum(
        (pickup.actual_weight or Decimal("0") for pickup in weighed_pickups),
        Decimal("0"),
    )
    total_actual_reward = Decimal("0")
    unpriced_verified_count = 0
    for record in [*verified_submissions, *verified_pickups]:
        reward = record.actual_reward
        if reward is None:
            unpriced_verified_count += 1
        else:
            total_actual_reward += reward

    return {
        "activity": activity,
        "total_submissions": len(submissions),
        "total_pickups": len(pickups),
        "total_activity": len(activity),
        "total_actual_weight": total_actual_weight,
        "total_actual_reward": total_actual_reward,
        "verified_count": len(verified_submissions) + len(weighed_pickups),
        "unpriced_verified_count": unpriced_verified_count,
    }
