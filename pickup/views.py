import uuid

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.http import JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction

from pickup import services
from pickup.models import PickupRequest
from pickup.forms import PickupRequestForm, PickupWeighingFormSet
from pickup.permissions import is_giver, is_collector, is_admin


# Create your views here.

Status = PickupRequest.Status

# Status yang boleh dituju lewat endpoint update status (bukan cancel/accept).
PROGRESS_STATUSES = {
  Status.PENDING,
  Status.ON_THE_WAY,
  Status.ARRIVED,
  Status.WEIGHING,
  Status.FAILED,
}


def _action(status, label, danger=False, needs_note=False):
  return {"status": status.value, "label": label, "danger": danger, "needs_note": needs_note}


COLLECTOR_ACTIONS = {
  Status.ASSIGNED.value: (
    _action(Status.ON_THE_WAY, "Berangkat menjemput"),
  ),
  Status.ON_THE_WAY.value: (
    _action(Status.ARRIVED, "Tandai sudah tiba"),
    _action(Status.FAILED, "Tandai gagal", danger=True, needs_note=True),
  ),
  Status.ARRIVED.value: (
    _action(Status.WEIGHING, "Mulai penimbangan"),
    _action(Status.FAILED, "Tandai gagal", danger=True, needs_note=True),
  ),
  Status.WEIGHING.value: (
    _action(Status.FAILED, "Tandai gagal", danger=True, needs_note=True),
  ),
}


VALID_SCOPES = {"mine", "available"}


# ---------- Helper ----------


def _display_name(user):
  if user is None:
    return None
  return user.get_full_name() or user.get_username()


def _apply_filters(queryset, request):
  status = request.GET.get("status", "").strip()
  query = request.GET.get("q", "").strip()

  if status:
    if status in Status.values:
      queryset = queryset.filter(status=status)
    else:
      queryset = queryset.none()

  if query:
    try:
      queryset = queryset.filter(pk=uuid.UUID(query))
    except ValueError:
      queryset = queryset.none()

  return queryset


def _get_accessible_pickup(user, pickup_id):
  pickup = get_object_or_404(
    PickupRequest.objects.select_related("giver", "collector").prefetch_related(
      "items__waste_type", "status_history__changed_by"
    ),
    pk=pickup_id,
  )
  is_owner = pickup.giver_id == user.pk
  is_assigned = pickup.collector_id == user.pk
  is_available = is_collector(user) and pickup.status == Status.PENDING

  if not (is_owner or is_assigned or is_available or is_admin(user)):
    raise Http404

  return pickup, is_owner, is_assigned


def _transition_response(request, pickup_id, new_status, note="", collector=None):
  try:
    pickup = services.change_status(
      pickup_id, new_status, request.user, reason=note, collector=collector
    )
  except PermissionDenied:
    return JsonResponse({"error": "Anda tidak memiliki akses."}, status=403)
  except services.PickupServiceError as e:
    return JsonResponse({"error": e.message}, status=e.status_code)

  return JsonResponse(
    {
      "message": "Status pickup berhasil diperbarui.",
      "pk": str(pickup.id),
      "status": pickup.status,
      "status_display": pickup.get_status_display(),
    }
  )


def _get_today_string():
  today = timezone.localdate()

  months = [
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des"
  ]

  return f"{today.day} {months[today.month - 1]} {today.year}"


def _get_current_month_string():
  today = timezone.localdate()

  months = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
  ]

  return f"{months[today.month - 1]} {today.year}"


# --------------- Page ---------------


@login_required(login_url="auth_page")
def show_pickup_list(request):
  if not is_giver(request.user):
    raise PermissionDenied
  return redirect(
    f"{reverse('waste:new')}?delivery_method=minta_dijemput"
  )


@login_required(login_url="auth_page")
def show_collector_pickup_list(request):
  if not is_collector(request.user):
    raise PermissionDenied
  
  id_query = request.GET.get("id", "").strip()

  context = {
    "id_query": id_query,
    "collector_name": request.user.first_name,
    "today_date": _get_today_string(),
    "current_month": _get_current_month_string(),
  }

  return render(request, "pickup/dashboard_collector.html", context)


@login_required(login_url="auth_page")
def show_collector_pickup_history(request):
  if not is_collector(request.user):
    raise PermissionDenied

  pickups = (
    PickupRequest.objects.filter(collector=request.user)
    .select_related("giver")
    .prefetch_related("items__waste_type", "status_history__changed_by")
  )
  return render(
    request,
    "pickup/collector_history.html",
    {"active_item": "history", "pickups": pickups},
  )


def request_pickup(request):
  return render(request, "waste/request.html", {"active_item": "waste"})


@login_required(login_url="auth_page")
def show_pickup_detail(request, pickup_id):
  pickup, is_owner, is_assigned = _get_accessible_pickup(request.user, pickup_id)
  user_is_admin = is_admin(request.user)

  can_accept = (
    is_collector(request.user)
    and pickup.status == Status.PENDING
    and pickup.collector_id is None
  )
  can_see_contact = is_owner or is_assigned or user_is_admin
  can_cancel = pickup.is_cancellable and (is_owner or user_is_admin)

  collector_actions = COLLECTOR_ACTIONS.get(pickup.status, ()) if is_assigned else ()

  weighing_formset = None
  if is_assigned and pickup.status == Status.WEIGHING:
    weighing_formset = PickupWeighingFormSet(
      queryset=pickup.items.all(), prefix="weigh"
    )

  context = {
    "active_item": "history",
    "submission_id": pickup_id,
    "pickup": pickup,
    "payout_pending": pickup.status == Status.COMPLETED and pickup.verified_at is None,
    "is_owner": is_owner,
    "is_assigned": is_assigned,
    "can_accept": can_accept,
    "can_cancel": can_cancel,
    "can_see_contact": can_see_contact,
    "collector_actions": collector_actions,
    "weighing_formset": weighing_formset,
  }

  return render(request, "pickup/detail.html", context)
  

# ---------- API: read ----------


def get_pickup_json(request):
  if not request.user.is_authenticated:
    return JsonResponse({"error": "Autentikasi diperlukan."}, status=401)
  if not is_giver(request.user):
    return JsonResponse({"error": "Anda tidak memiliki akses."}, status=403)
  
  pickup_list = PickupRequest.objects.filter(giver=request.user).select_related("collector")
  pickup_list = _apply_filters(pickup_list, request)

  data = []
  for pickup in pickup_list:
    data.append({
      "pk": str(pickup.id),
      "fields": {
        "status": pickup.status,
        "status_display": pickup.get_status_display(),
        "scheduled_date": pickup.scheduled_date,
        "time_slot": pickup.time_slot,
        "pickup_address": pickup.pickup_address,
        "address_detail": pickup.address_detail,
        "collector_name": _display_name(pickup.collector),
      }
    })

  return JsonResponse(data, safe=False)


def get_collector_pickup_json(request):
  if not request.user.is_authenticated:
    return JsonResponse({"error": "Autentikasi diperlukan."}, status=401)
  if not is_collector(request.user):
    return JsonResponse({"error": "Anda tidak memiliki akses."}, status=403)

  scope = request.GET.get("scope", "mine").strip()
  if scope not in VALID_SCOPES:
    return JsonResponse({"error": "Scope tidak valid."}, status=400)

  if scope == "available":
    pickup_list = PickupRequest.objects.filter(
      status=Status.PENDING, collector__isnull=True
    )
  else:
    pickup_list = PickupRequest.objects.filter(collector=request.user)

  pickup_list = _apply_filters(
    pickup_list.select_related("giver").prefetch_related("items__waste_type"),
    request,
  )
  
  data = []
  for pickup in pickup_list:
    data.append({
      "pk": str(pickup.id),
      "fields": {
        "status": pickup.status,
        "status_display": pickup.get_status_display(),
        "scheduled_date": pickup.scheduled_date,
        "time_slot": pickup.time_slot,
        "pickup_address": pickup.pickup_address,
        "address_detail": pickup.address_detail,
        "pickup_address": pickup.pickup_address,
        "completed_at": pickup.completed_at,
        "estimated_weight": str(pickup.estimated_weight),
        "actual_weight": str(pickup.actual_weight) if pickup.actual_weight is not None else None,
        "items": [item.waste_type.name for item in pickup.items.all()],
        "giver_name": _display_name(pickup.giver),
      }
    })

  return JsonResponse(data, safe=False)


def get_pickup_detail_json(request, pickup_id):
  if not request.user.is_authenticated:
    return JsonResponse({"error": "Autentikasi diperlukan."}, status=401)

  pickup, is_owner, is_assigned = _get_accessible_pickup(request.user, pickup_id)
  can_see_contact = is_owner or is_assigned or is_admin(request.user)

  history = []
  for item in pickup.status_history.all():
    history.append({
      "previous_status": item.previous_status,
      "new_status": item.new_status,
      "new_status_display": item.get_new_status_display(),
      "changed_by": _display_name(item.changed_by),
      "note": item.note,
      "created_at": item.created_at,
    })

  data = {
    "pk": str(pickup.id),
    "fields": {
      "giver_name": _display_name(pickup.giver),
      "collector_name": _display_name(pickup.collector),
      "pickup_address": pickup.pickup_address,
      "address_detail": pickup.address_detail,
      "latitude": float(pickup.latitude) if pickup.latitude is not None else None,
      "longitude": float(pickup.longitude) if pickup.longitude is not None else None,
      "contact_phone": pickup.contact_phone if can_see_contact else None,
      "scheduled_date": pickup.scheduled_date,
      "time_slot": pickup.time_slot,
      "status": pickup.status,
      "status_display": pickup.get_status_display(),
      "status_reason": pickup.status_reason,
      "is_cancellable": pickup.is_cancellable and (is_owner or is_admin(request.user)),
    },
    "history": history,
  }

  return JsonResponse(data)


# ---------- API: action ----------


@require_POST
def create_pickup_ajax(request):
  if not request.user.is_authenticated:
    return JsonResponse({"error": "Autentikasi diperlukan."}, status=401)
  if not is_giver(request.user):
    return JsonResponse({"error": "Anda tidak memiliki akses."}, status=403)

  form = PickupRequestForm(request.POST)
  if not form.is_valid():
    return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

  pickup = services.create_pickup(form.save(commit=False), request.user)
  return JsonResponse(
    {"message": "Permintaan pickup berhasil ditambahkan.", "pk": str(pickup.id)},
    status=201,
  )


@require_POST
def cancel_pickup_ajax(request, pickup_id):
  if not request.user.is_authenticated:
    return JsonResponse({"error": "Autentikasi diperlukan."}, status=401)

  reason = request.POST.get("reason", "").strip()
  return _transition_response(request, pickup_id, Status.CANCELLED, note=reason)


@require_POST
def accept_pickup_ajax(request, pickup_id):
  if not request.user.is_authenticated:
    return JsonResponse({"error": "Autentikasi diperlukan."}, status=401)
  if not is_collector(request.user):
    return JsonResponse({"error": "Anda tidak memiliki akses."}, status=403)

  return _transition_response(
    request, pickup_id, Status.ASSIGNED, collector=request.user
  )


@require_POST
def update_pickup_status_ajax(request, pickup_id):
  if not request.user.is_authenticated:
    return JsonResponse({"error": "Autentikasi diperlukan."}, status=401)

  new_status = request.POST.get("status", "").strip()
  if new_status not in PROGRESS_STATUSES:
    return JsonResponse({"error": "Status tujuan tidak valid."}, status=400)

  note = request.POST.get("note", "").strip()
  return _transition_response(request, pickup_id, new_status, note=note)


@require_POST
def complete_weighing_ajax(request, pickup_id):
  if not request.user.is_authenticated:
    return JsonResponse({"error": "Autentikasi diperlukan."}, status=401)

  pickup = get_object_or_404(
    PickupRequest.objects.prefetch_related("items__waste_type"), pk=pickup_id
  )
  if pickup.collector_id != request.user.pk and not is_admin(request.user):
    return JsonResponse({"error": "Anda tidak memiliki akses."}, status=403)
  if pickup.status != Status.WEIGHING:
    return JsonResponse({"error": "Pickup belum berada pada tahap penimbangan."}, status=400)

  formset = PickupWeighingFormSet(
    request.POST, queryset=pickup.items.all(), prefix="weigh"
  )
  if not formset.is_valid():
    return JsonResponse(
      {
        "error": "Periksa kembali berat aktual yang diisi.",
        "form_errors": [form.errors.get_json_data() for form in formset.forms],
        "non_form_errors": list(formset.non_form_errors()),
      },
      status=400,
    )

  try:
    with transaction.atomic():
      formset.save()
      pickup = services.change_status(
        pickup_id, Status.COMPLETED, request.user, reason="", collector=None
      )
      pickup = services.verify_completed_pickup(pickup.pk, request.user)
  except PermissionDenied:
    return JsonResponse({"error": "Anda tidak memiliki akses."}, status=403)
  except services.PickupServiceError as e:
    return JsonResponse({"error": e.message}, status=e.status_code)

  return JsonResponse(
    {
      "message": "Pickup selesai diverifikasi dan insentif berhasil diproses.",
      "pk": str(pickup.id),
      "status": pickup.status,
      "status_display": pickup.get_status_display(),
    }
  )
