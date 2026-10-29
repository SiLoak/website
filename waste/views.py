from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from pickup.models import PickupRequest, PickupStatusHistory
from .forms import SubmissionForm, SubmissionItemFormSet
from pickup.forms import PickupRequestForm, PickupItemFormSet
from .models import Submission
from wallet.models import Wallet

PICKUP_PREFILL_FIELDS = ("address_detail", "contact_phone", "latitude", "longitude")


def _saved_pickup_initial(user):
    saved_pickup = (
        PickupRequest.objects.filter(
            giver=user,
            latitude__isnull=False,
            longitude__isnull=False,
        )
        .order_by("-created_at")
        .first()
    )
    if saved_pickup is None:
        return {}
    return {name: getattr(saved_pickup, name) for name in PICKUP_PREFILL_FIELDS}

def _create_pickup_request(request, pickup_form, formset):
    with transaction.atomic():
        pickup = pickup_form.save(commit=False)
        pickup.giver = request.user
        pickup.save()

        formset.instance = pickup
        for item in formset.save(commit=False):
            item.unit_rate_snapshot = item.waste_type.rate_per_kg
            item.save()

        PickupStatusHistory.objects.create(
            pickup=pickup,
            previous_status="",
            new_status=pickup.status,
            changed_by=request.user,
            note="Permintaan penjemputan dibuat.",
        )

    return pickup

def _submission_form_view(request, submission=None):
    editing = submission is not None
    if editing and submission.status != Submission.Status.PENDING:
        messages.error(request, "Pengajuan ini sudah tidak dapat diubah.")
        return redirect("waste:detail", submission_id=submission.pk)

    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    is_pickup = (
        request.method == "POST"
        and not editing
        and request.POST.get("delivery_method") == "minta_dijemput"
    )

    if is_pickup:
        form = SubmissionForm()
        pickup_form = PickupRequestForm(request.POST)
        formset = PickupItemFormSet(request.POST)
        incentive_form = pickup_form
    else:
        form = SubmissionForm(request.POST or None, initial={"incentive_allocation": wallet.default_incentive})

        pickup_form = PickupRequestForm(
            initial={} if editing else _saved_pickup_initial(request.user)
        )
        formset = SubmissionItemFormSet(request.POST or None, instance=submission)
        incentive_form = form

    if is_pickup and pickup_form.is_valid() and formset.is_valid():
        pickup = _create_pickup_request(request, pickup_form, formset)
        messages.success(request, "Permintaan penjemputan berhasil dibuat.")
        return redirect("pickup:show_pickup_detail", pickup_id=pickup.pk)

    if request.method == "POST" and not is_pickup and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            saved_submission = form.save(commit=False)
            if not editing:
                saved_submission.user = request.user
            saved_submission.save()

            formset.instance = saved_submission
            formset.save(commit=False)
            for deleted_item in formset.deleted_objects:
                deleted_item.delete()

            for item_form in formset.forms:
                if (
                    not item_form.cleaned_data
                    or item_form.cleaned_data.get("DELETE")
                    or not item_form.has_changed()
                ):
                    continue
                item = item_form.save(commit=False)
                item.submission = saved_submission
                if not item.pk or "waste_type" in item_form.changed_data:
                    item.unit_rate_snapshot = item.waste_type.rate_per_kg
                item.save()

        messages.success(
            request,
            "Pengajuan berhasil diperbarui." if editing else "Pengajuan setoran berhasil dibuat.",
        )
        return redirect("waste:detail", submission_id=saved_submission.pk)

    return render(
        request,
        "waste/dropoff.html",
        {
            "active_item": "waste",
            "form": form,
            "pickup_form": pickup_form,
            "incentive_form": incentive_form,
            "formset": formset,
            "editing": editing,
            "submission": submission,
        },
    )


@login_required(login_url="auth_page")
def new_submission(request):
    return _submission_form_view(request)


@login_required(login_url="auth_page")
def dropoff_submission(request):
    return _submission_form_view(request)


@login_required(login_url="auth_page")
def edit_submission(request, submission_id):
    submission = get_object_or_404(
        Submission, pk=submission_id, user=request.user
    )
    return _submission_form_view(request, submission)


@login_required(login_url="auth_page")
@require_POST
def cancel_submission(request, submission_id):
    submission = get_object_or_404(
        Submission, pk=submission_id, user=request.user
    )
    if submission.status != Submission.Status.PENDING:
        messages.error(request, "Hanya pengajuan yang menunggu penimbangan yang dapat dibatalkan.")
    else:
        submission.status = Submission.Status.CANCELED
        submission.canceled_at = timezone.now()
        submission.save(update_fields=["status", "canceled_at", "updated_at"])
        messages.success(request, "Pengajuan setoran berhasil dibatalkan.")
    return redirect("waste:detail", submission_id=submission.pk)


@login_required(login_url="auth_page")
def submission_detail(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.select_related("collection_point", "user")
        .prefetch_related("items__waste_type"),
        pk=submission_id,
        user=request.user,
    )
    return render(
        request,
        "waste/detail.html",
        {"active_item": "history", "submission": submission},
    )


@login_required(login_url="auth_page")
def submission_history(request):
    submissions = list(
        Submission.objects.filter(user=request.user)
        .select_related("collection_point")
        .prefetch_related("items__waste_type")
    )
    verified = [
        submission
        for submission in submissions
        if submission.status == Submission.Status.VERIFIED
    ]
    total_actual_weight = sum(
        (submission.actual_weight or Decimal("0") for submission in verified),
        Decimal("0"),
    )
    unpriced_verified_count = sum(
        1 for submission in verified if submission.actual_reward is None
    )
    total_actual_reward = sum(
        (submission.actual_reward or Decimal("0") for submission in verified),
        Decimal("0"),
    )
    return render(
        request,
        "history.html",
        {
            "active_item": "history",
            "submissions": submissions,
            "total_submissions": len(submissions),
            "verified_count": len(verified),
            "total_actual_weight": total_actual_weight,
            "total_actual_reward": total_actual_reward,
            "unpriced_verified_count": unpriced_verified_count,
        },
    )
