"""Small helpers for answering HTMX requests."""

import json

from django.http import HttpResponse

PAGE_ROOT = "#page-root"


def is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def with_toast(response, message, level="success"):
    """Ask the page to show a toast (handled in static/js/siloak/htmx-setup.js)."""
    response["HX-Trigger"] = json.dumps({"showToast": {"message": message, "level": level}})
    return response


def hx_location(path):
    """Load ``path`` into the page without a full reload, and update the URL."""
    response = HttpResponse(status=200)
    response["HX-Location"] = json.dumps(
        {"path": path, "target": PAGE_ROOT, "select": PAGE_ROOT, "swap": "outerHTML"}
    )
    return response
