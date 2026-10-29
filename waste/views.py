from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, QueryDict
from django.urls import reverse
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.http import require_POST

from pickup.models import PickupRequest, PickupStatusHistory
from .forms import SubmissionForm, SubmissionItemFormSet
from pickup.forms import PickupRequestForm, PickupItemFormSet
from .models import Submission
from .history import (
    PAGE_SIZE,
    HistoryFilterForm,
    build_history,
    cancel_entries,
    entry_for,
    history_stats,
    parse_selection,
)
from wallet.models import Wallet
from main.htmx import hx_location, is_htmx, with_toast
from main.security import rate_limit

PICKUP_PREFILL_FIELDS = (
    "pickup_address",
    "address_detail",
    "contact_phone",
    "latitude",
    "longitude",
)


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
    initial = {}
    if saved_pickup is not None:
        initial = {name: getattr(saved_pickup, name) for name in PICKUP_PREFILL_FIELDS}
    if not initial.get("contact_phone"):
        profile = getattr(user, "profile", None)
        if profile is not None and profile.phone_number:
            initial["contact_phone"] = profile.phone_number
    return initial


def _pickup_date_choices():
    today = timezone.localdate()
    labels = (("today", "Hari ini"), ("tomorrow", "Besok"), ("day_after", "Lusa"))
    return [
        {
            "value": value,
            "label": label,
            "date_label": date_format(today + timedelta(days=offset), "D, j M"),
        }
        for offset, (value, label) in enumerate(labels)
    ]

def _save_items(formset, parent):
    """Save formset items, deleting removed rows and snapshotting new rates."""
    formset.instance = parent
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
        if not item.pk or "waste_type" in item_form.changed_data:
            item.unit_rate_snapshot = item.waste_type.rate_per_kg
        item.save()


def _save_pickup_request(request, pickup_form, formset, editing):
    with transaction.atomic():
        pickup = pickup_form.save(commit=False)
        if not editing:
            pickup.giver = request.user
        pickup.save()
        _save_items(formset, pickup)
        PickupStatusHistory.objects.create(
            pickup=pickup,
            previous_status="" if not editing else pickup.status,
            new_status=pickup.status,
            changed_by=request.user,
            note="Permintaan penjemputan diperbarui." if editing else "Permintaan penjemputan dibuat.",
        )
    return pickup


def _save_submission(request, form, formset, editing):
    with transaction.atomic():
        submission = form.save(commit=False)
        if not editing:
            submission.user = request.user
        submission.save()
        _save_items(formset, submission)
    return submission


def _after_save(request, path):
    return hx_location(path) if is_htmx(request) else redirect(path)


def _submission_form_view(request, submission=None, pickup=None):
    """One form for three jobs: new setoran/pickup, edit setoran, edit pickup."""
    if submission is not None and submission.status != Submission.Status.PENDING:
        messages.error(request, "Pengajuan ini sudah tidak dapat diubah.")
        return redirect("waste:detail", submission_id=submission.pk)
    if pickup is not None and pickup.status != PickupRequest.Status.PENDING:
        messages.error(request, "Pickup yang sudah diproses petugas tidak dapat diubah.")
        return redirect("pickup:show_pickup_detail", pickup_id=pickup.pk)

    editing = submission is not None
    editing_pickup = pickup is not None
    data = request.POST if request.method == "POST" else None
    wallet, _ = Wallet.objects.get_or_create(user=request.user)

    if editing_pickup:
        delivery_method = "minta_dijemput"
    elif editing:
        delivery_method = "antar_sendiri"
    else:
        delivery_method = (data or {}).get("delivery_method") or "antar_sendiri"
    is_pickup = delivery_method == "minta_dijemput"

    if is_pickup:
        form = SubmissionForm()
        pickup_form = PickupRequestForm(data, instance=pickup)
        formset = PickupItemFormSet(data, instance=pickup)
        incentive_form = pickup_form
    else:
        form = SubmissionForm(
            data, instance=submission,
            initial={"incentive_allocation": wallet.default_incentive},
        )
        pickup_form = PickupRequestForm(initial=_saved_pickup_initial(request.user))
        formset = SubmissionItemFormSet(data, instance=submission)
        incentive_form = form

    if data is not None:
        if is_pickup and pickup_form.is_valid() and formset.is_valid():
            saved = _save_pickup_request(request, pickup_form, formset, editing_pickup)
            messages.success(
                request,
                "Permintaan penjemputan berhasil diperbarui." if editing_pickup
                else "Permintaan penjemputan berhasil dibuat.",
            )
            return _after_save(request, reverse("pickup:show_pickup_detail", args=[saved.pk]))
        if not is_pickup and form.is_valid() and formset.is_valid():
            saved = _save_submission(request, form, formset, editing)
            messages.success(
                request,
                "Pengajuan berhasil diperbarui." if editing else "Pengajuan setoran berhasil dibuat.",
            )
            return _after_save(request, reverse("waste:detail", args=[saved.pk]))

    # 422 lets HTMX swap the form back in with its errors.
    status = 422 if data is not None and is_htmx(request) else 200
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
            "editing_pickup": editing_pickup,
            "submission": submission,
            "pickup": pickup,
            "delivery_method": delivery_method,
            "pickup_dates": _pickup_date_choices(),
        },
        status=status,
    )


@login_required(login_url="auth_page")
@rate_limit("submission-create", "10/m")
def new_submission(request):
    return _submission_form_view(request)


@login_required(login_url="auth_page")
@rate_limit("submission-create", "10/m")
def dropoff_submission(request):
    return _submission_form_view(request)


@login_required(login_url="auth_page")
@rate_limit("submission-edit", "20/m")
def edit_submission(request, submission_id):
    submission = get_object_or_404(
        Submission, pk=submission_id, user=request.user
    )
    return _submission_form_view(request, submission)


@login_required(login_url="auth_page")
@require_POST
@rate_limit("submission-cancel", "10/m")
def cancel_submission(request, submission_id):
    submission = get_object_or_404(Submission, pk=submission_id, user=request.user)
    if submission.status != Submission.Status.PENDING:
        message = "Hanya pengajuan yang menunggu penimbangan yang dapat dibatalkan."
        if is_htmx(request):
            return HttpResponse(message, status=409, content_type="text/plain; charset=utf-8")
        messages.error(request, message)
        return redirect("waste:detail", submission_id=submission.pk)

    cancel_entries(request.user, [submission.pk], [], reason="")
    if is_htmx(request):
        return with_toast(_render_detail(request, submission.pk), "Pengajuan setoran berhasil dibatalkan.")
    messages.success(request, "Pengajuan setoran berhasil dibatalkan.")
    return redirect("waste:detail", submission_id=submission.pk)


def _render_detail(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.select_related("collection_point", "user")
        .prefetch_related("items__waste_type"),
        pk=submission_id,
        user=request.user,
    )
    return render(request, "waste/detail.html", {"active_item": "history", "submission": submission})


@login_required(login_url="auth_page")
def submission_detail(request, submission_id):
    return _render_detail(request, submission_id)


def _history_context(request, params):
    filter_form = HistoryFilterForm(params)
    entries = build_history(request.user, filter_form.filters())
    page_obj = Paginator(entries, PAGE_SIZE).get_page(params.get("page"))
    query = params.copy()
    query.pop("page", None)
    return {
        "active_item": "history",
        "filter_form": filter_form,
        "page_obj": page_obj,
        "filter_query": query.urlencode(),
        "stats": history_stats(request.user),
        "is_htmx": is_htmx(request),
    }


def _render_history(request, params, status=200):
    context = _history_context(request, params)
    template = "waste/partials/history_results.html" if is_htmx(request) else "history.html"
    return render(request, template, context, status=status)


@login_required(login_url="auth_page")
def submission_history(request):
    return _render_history(request, request.GET)


@login_required(login_url="auth_page")
@require_POST
@rate_limit("history-bulk-cancel", "5/m")
def bulk_cancel(request):
    dropoff_ids, pickup_ids = parse_selection(request.POST.getlist("selected"))
    count = cancel_entries(request.user, dropoff_ids, pickup_ids, reason="Dibatalkan dari riwayat.")
    if count:
        message, level = f"{count} pengajuan berhasil dibatalkan.", "success"
    else:
        message, level = "Tidak ada pengajuan yang dapat dibatalkan dari pilihanmu.", "warning"

    if is_htmx(request):
        # Re-render the list with the filters the user is looking at.
        params = QueryDict(request.POST.get("filter_query", ""))
        return with_toast(_render_history(request, params), message, level)
    getattr(messages, level)(request, message)
    return redirect("waste:submissions")


@login_required(login_url="auth_page")
@require_POST
@rate_limit("history-cancel", "20/m")
def cancel_entry(request):
    """Cancel one history row (drop-off or pickup) and send back the new row."""
    dropoff_ids, pickup_ids = parse_selection([request.POST.get("entry", "")])
    kind, pk = ("dropoff", dropoff_ids[0]) if dropoff_ids else ("pickup", pickup_ids[0]) if pickup_ids else (None, None)
    entry = entry_for(request.user, kind, pk) if kind else None
    if entry is None:
        raise Http404
    if not entry.cancellable:
        message = "Pengajuan ini sudah tidak dapat dibatalkan."
        if is_htmx(request):
            return HttpResponse(message, status=409, content_type="text/plain; charset=utf-8")
        messages.error(request, message)
        return redirect("waste:submissions")

    cancel_entries(request.user, dropoff_ids, pickup_ids, reason="Dibatalkan dari riwayat.")
    message = f"Pengajuan {entry.number} dibatalkan."
    if not is_htmx(request):
        messages.success(request, message)
        return redirect("waste:submissions")
    response = render(request, "waste/partials/history_row_swap.html", {
        "entry": entry_for(request.user, kind, pk),
        "stats": history_stats(request.user),
    })
    return with_toast(response, message)
