"""Reusable security decorators for SiLoak views.

- ``ajax_login_required``: JSON 401 instead of a login redirect for API views.
- ``giver_required`` / ``collector_required``: role checks for pages or JSON APIs.
- ``rate_limit``: per-user (or per-IP) limit on state-changing requests.
"""

import time
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from pickup.permissions import is_collector, is_giver

LOGIN_URL = "auth_page"
UNAUTHENTICATED_MESSAGE = "Autentikasi diperlukan."
FORBIDDEN_MESSAGE = "Anda tidak memiliki akses."
RATE_LIMIT_MESSAGE = "Terlalu banyak permintaan. Coba lagi dalam {seconds} detik."
RATE_PERIODS = {"s": 1, "m": 60, "h": 3600}


def _wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


def ajax_login_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": UNAUTHENTICATED_MESSAGE}, status=401)
        return view(request, *args, **kwargs)

    return wrapper


def role_required(check, *, json=False):
    """Allow the view only when ``check(user)`` is true.

    Anonymous users go to the login page (or get 401 in JSON mode); signed-in
    users without the role get 403.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                if json:
                    return JsonResponse({"error": UNAUTHENTICATED_MESSAGE}, status=401)
                return redirect_to_login(request.get_full_path(), LOGIN_URL)
            if not check(user):
                if json or _wants_json(request):
                    return JsonResponse({"error": FORBIDDEN_MESSAGE}, status=403)
                return render(request, "403.html", status=403)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def giver_required(*, json=False):
    return role_required(is_giver, json=json)


def collector_required(*, json=False):
    return role_required(is_collector, json=json)


def _parse_rate(rate):
    try:
        count, period = rate.split("/")
        return int(count), RATE_PERIODS[period]
    except (ValueError, KeyError):
        raise ValueError(f"Rate tidak valid: {rate!r}. Contoh: '10/m'.") from None


def _client_key(request):
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    return f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"


def rate_limit(scope, rate, methods=("POST",)):
    """Fixed-window rate limit, e.g. ``@rate_limit("pickup-create", "5/m")``.

    Only ``methods`` count toward the limit, so reading a page never locks a
    user out. Blocked requests get 429 with a ``Retry-After`` header.
    """
    limit, period = _parse_rate(rate)

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return view(request, *args, **kwargs)

            window = int(time.time() // period)
            key = f"rate:{scope}:{_client_key(request)}:{window}"
            cache.add(key, 0, timeout=period)
            try:
                count = cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=period)
                count = 1

            if count > limit:
                message = RATE_LIMIT_MESSAGE.format(seconds=period)
                if _wants_json(request):
                    response = JsonResponse({"error": message}, status=429)
                else:
                    response = HttpResponse(message, status=429, content_type="text/plain; charset=utf-8")
                response["Retry-After"] = str(period)
                return response
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
