from django.shortcuts import render
from waste.models import CollectionPoint


def location_list(request):
    points = list(
        CollectionPoint.objects.filter(is_active=True)
        .exclude(latitude__isnull=True)
        .exclude(longitude__isnull=True)
        .values("id", "name", "address", "latitude", "longitude", "operating_hours")
    )
    return render(request, "location/index.html", {"active_item": "location", "map_points": points})
