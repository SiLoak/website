import uuid

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.views.decorators.http import require_POST

from pickup import services
from pickup.models import PickupRequest
from pickup.forms import PickupForm
from pickup.permissions import is_giver, is_collector, is_admin

# Create your views here.

Status = PickupRequest.Status

# Status yang boleh dituju lewat endpoint update status (bukan cancel/accept).
PROGRESS_STATUSES = {
  Status.PENDING,
  Status.ON_THE_WAY,
  Status.ARRIVED,
  Status.WEIGHING,
  Status.COMPLETED,
  Status.FAILED,
}


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
    PickupRequest.objects.select_related("giver", "collector"), pk=pickup_id
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


# --------------- Page ---------------


def show_pickup_list(request):
  if not request.user.is_authenticated:
    return redirect_to_login(request.get_full_path())
  if not is_giver(request.user):
    raise PermissionDenied
  
  id_query = request.GET.get("id", "").strip()

  context = {
    "id_query": id_query,
    "form": PickupForm(),
  }

  return render(request, "pickup.html", context)


def show_collector_pickup_list(request):
  if not request.user.is_authenticated:
    return redirect_to_login(request.get_full_path())
  if not is_collector(request.user):
    raise PermissionDenied
  
  id_query = request.GET.get("id", "").strip()

  context = {
    "id_query": id_query,
  }

  return render(request, "collector_pickup.html", context)
  

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
        "scheduled_at": pickup.scheduled_at,
        "address": pickup.pickup_address,
        "collector_name": _display_name(pickup.collector),
      }
    })

  return JsonResponse(data, safe=False)


def get_collector_pickup_json(request):
  if not request.user.is_authenticated:
    return JsonResponse({"error": "Autentikasi diperlukan."}, status=401)
  if not is_collector(request.user):
    return JsonResponse({"error": "Anda tidak memiliki akses."}, status=403)

  if request.GET.get("scope", "mine") == "available":
    pickup_list = PickupRequest.objects.filter(
      status=Status.PENDING, collector__isnull=True
    )
  else:
    pickup_list = PickupRequest.objects.filter(collector=request.user)

  pickup_list = _apply_filters(pickup_list.select_related("giver"), request)
  
  data = []
  for pickup in pickup_list:
    data.append({
      "pk": str(pickup.id),
      "fields": {
        "status": pickup.status,
        "status_display": pickup.get_status_display(),
        "scheduled_at": pickup.scheduled_at,
        "address": pickup.pickup_address,
        "giver_name": _display_name(pickup.giver),
        "item_description": pickup.item_description,
      }
    })

  return JsonResponse(data, safe=False)


def get_pickup_detail_json(request, pickup_id):
  if not request.user.is_authenticated:
    return JsonResponse({"error": "Autentikasi diperlukan."}, status=401)

  pickup, is_owner, is_assigned = _get_accessible_pickup(request.user, pickup_id)
  can_see_contact = is_owner or is_assigned or is_admin(request.user)

  history = []
  for item in pickup.status_history.select_related("changed_by"):
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
      "address": pickup.pickup_address,
      "address_detail": pickup.address_detail,
      "latitude": float(pickup.latitude) if pickup.latitude is not None else None,
      "longitude": float(pickup.longitude) if pickup.longitude is not None else None,
      "contact_phone": pickup.contact_phone if can_see_contact else None,
      "scheduled_at": pickup.scheduled_at,
      "item_description": pickup.item_description,
      "giver_note": pickup.giver_note,
      "collector_note": pickup.collector_note,
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

  form = PickupForm(request.POST)
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
  new_status = request.POST.get("status", "").strip()
  if new_status not in PROGRESS_STATUSES:
    return JsonResponse({"error": "Status tujuan tidak valid."}, status=400)

  note = request.POST.get("note", "").strip()
  return _transition_response(request, pickup_id, new_status, note=note)