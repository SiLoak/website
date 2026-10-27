from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import SubmissionForm, SubmissionItemFormSet
from .models import Submission


def _submission_form_view(request, submission=None):
    editing = submission is not None
    if editing and submission.status != Submission.Status.PENDING:
        messages.error(request, "Pengajuan ini sudah tidak dapat diubah.")
        return redirect("waste:detail", submission_id=submission.pk)

    form = SubmissionForm(request.POST or None, instance=submission)
    formset = SubmissionItemFormSet(request.POST or None, instance=submission)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
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
