"""Template helpers so other modules can show collection points the same way."""

from django import template
from django.utils import timezone

from location import services

register = template.Library()


@register.filter
def point_info(point):
    """Category, clean address, and opening status of a CollectionPoint.

    ``is_open`` is None and ``opening_label`` is empty when the point has no
    known opening hours, so templates can simply skip the hours.
    """
    status = services.opening_status(point.operating_hours, timezone.localtime())
    category, label = services.categorize(point.name)
    known = status["is_open"] is not None
    address = point.address if point.address and point.address != services.PLACEHOLDER_ADDRESS else ""
    return {
        "category": category,
        "category_label": label,
        "address": address,
        "is_open": status["is_open"],
        "opening_label": status["label"] if known else "",
    }
