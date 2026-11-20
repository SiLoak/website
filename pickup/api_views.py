from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
  api_view, authentication_classes, permission_classes,
)
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from pickup import services
from pickup.models import PickupRequest
from pickup.permissions import IsGiver, IsCollector, is_admin
from pickup.serializers import (
  PickupCancelSerializer,
  PickupRequestCreateSerializer,
  PickupRequestListSerializer,
  PickupRequestSerializer,
  PickupStatusUpdateSerializer,
  PickupWeighingSerializer,
)
from pickup.views import VALID_SCOPES, _apply_filters, _get_accessible_pickup

Status = PickupRequest.Status

# ---------- Helper ----------

def _pickup_response(request, pickup_id, status_code=status.HTTP_200_OK):
  pickup, _, _ = _get_accessible_pickup(request.user, pickup_id)
  serializer = PickupRequestSerializer(pickup, context={"request": request})
  return Response(serializer.data, status=status_code)


def _transition(request, pickup_id, new_status, note="", collector=None):
  try:
    services.change_status(
      pickup_id, new_status, request.user, reason=note, collector=collector
    )
  except PermissionDenied:
    return Response(
      {"detail": "Anda tidak memiliki akses."}, status=status.HTTP_403_FORBIDDEN
    )
  except services.PickupServiceError as e:
    return Response({"detail": e.message}, status=e.status_code)

  return _pickup_response(request, pickup_id)


# ---------- Giver ----------

@api_view(["GET", "HEAD", "POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsGiver])
def pickup_list(request):
  if request.method in ("GET", "HEAD"):
    pickups = (
      PickupRequest.objects.filter(giver=request.user)
      .select_related("giver", "collector")
      .prefetch_related("items__waste_type")
    )
    pickups = _apply_filters(pickups, request)
    serializer = PickupRequestListSerializer(
      pickups, many=True, context={"request": request},
    )
    return Response(serializer.data)

  serializer = PickupRequestCreateSerializer(
    data=request.data, context={"request": request},
  )
  serializer.is_valid(raise_exception=True)
  serializer.save()
  return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------- Collector ----------

@api_view(["GET", "HEAD"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsCollector])
def collector_pickup_list(request):
  scope = request.query_params.get("scope", "mine").strip()
  if scope not in VALID_SCOPES:
    return Response(
      {"detail": "Scope tidak valid."}, status=status.HTTP_400_BAD_REQUEST
    )

  if scope == "available":
    pickups = PickupRequest.objects.filter(
      status=Status.PENDING, collector__isnull=True
    )
  else:
    pickups = PickupRequest.objects.filter(collector=request.user)

  pickups = _apply_filters(
    pickups.select_related("giver", "collector").prefetch_related(
      "items__waste_type"
    ),
    request,
  )
  serializer = PickupRequestListSerializer(
    pickups, many=True, context={"request": request},
  )
  return Response(serializer.data)


# ---------- Detail ----------

@api_view(["GET", "HEAD"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def pickup_detail(request, pickup_id):
  return _pickup_response(request, pickup_id)


# ---------- Actions ----------

@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def pickup_cancel(request, pickup_id):
  pickup, _, _ = _get_accessible_pickup(request.user, pickup_id)
  serializer = PickupCancelSerializer(
    data=request.data, context={"pickup": pickup},
  )
  serializer.is_valid(raise_exception=True)
  return _transition(
    request, pickup_id, Status.CANCELLED,
    note=serializer.validated_data["reason"],
  )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsCollector])
def pickup_accept(request, pickup_id):
  return _transition(
    request, pickup_id, Status.ASSIGNED, collector=request.user
  )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def pickup_status(request, pickup_id):
  pickup, _, _ = _get_accessible_pickup(request.user, pickup_id)
  serializer = PickupStatusUpdateSerializer(
    data=request.data, context={"pickup": pickup},
  )
  serializer.is_valid(raise_exception=True)
  return _transition(
    request, pickup_id, serializer.validated_data["status"],
    note=serializer.validated_data["note"],
  )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def pickup_weighing(request, pickup_id):
  pickup = get_object_or_404(
    PickupRequest.objects.prefetch_related("items__waste_type"), pk=pickup_id
  )
  if pickup.collector_id != request.user.pk and not is_admin(request.user):
    return Response(
      {"detail": "Anda tidak memiliki akses."}, status=status.HTTP_403_FORBIDDEN
    )

  serializer = PickupWeighingSerializer(
    data=request.data, context={"pickup": pickup},
  )
  serializer.is_valid(raise_exception=True)

  try:
    with transaction.atomic():
      serializer.save()
      services.change_status(
        pickup_id, Status.COMPLETED, request.user, reason="", collector=None
      )
      services.verify_completed_pickup(pickup.pk, request.user)
  except PermissionDenied:
    return Response(
      {"detail": "Anda tidak memiliki akses."}, status=status.HTTP_403_FORBIDDEN
    )
  except services.PickupServiceError as e:
    return Response({"detail": e.message}, status=e.status_code)

  return _pickup_response(request, pickup_id)