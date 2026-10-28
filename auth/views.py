import base64
import hashlib
import secrets
import uuid
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.http import require_GET
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from .forms import PhoneOnboardingForm
from .models import GoogleIdentity, UserProfile


GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
OAUTH_SESSION_KEY = "google_oauth_states"
MAX_PENDING_STATES = 5


def _oauth_error(request, message, next_url=""):
    messages.error(request, message)
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ""

    login_url = reverse("auth_page")
    if next_url:
        login_url = f"{login_url}?{urlencode({'next': next_url})}"
    return redirect(login_url)


def _safe_destination(request, destination):
    if url_has_allowed_host_and_scheme(
        destination, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destination
    return reverse("dashboard")


def complete_profile(request):
    if not request.user.is_authenticated:
        return redirect("auth_page")
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if profile.phone_number:
        return redirect("dashboard")

    next_url = request.GET.get("next", "")
    if request.method == "POST":
        next_url = request.POST.get("next", "")
        form = PhoneOnboardingForm(request.POST)
        if form.is_valid():
            profile.phone_number = form.cleaned_data["phone_number"]
            profile.save(update_fields=["phone_number"])
            return redirect(_safe_destination(request, next_url))
    else:
        form = PhoneOnboardingForm()
    return render(request, "auth/complete_profile.html", {"form": form, "next_url": next_url})


def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("landing_page")


def auth_page(request):
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        if not profile.phone_number:
            return redirect("complete_profile")
        return redirect("dashboard")

    next_url = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ""
    return render(request, "auth/login.html", {"next_url": next_url})


def _oauth_configuration():
    values = (
        getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", ""),
        getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", ""),
        getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", ""),
    )
    return values if all(values) else None


@require_GET
def google_login(request):
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        if not profile.phone_number:
            return redirect("complete_profile")
        return redirect("dashboard")

    next_url = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ""

    configuration = _oauth_configuration()
    if configuration is None:
        return _oauth_error(
            request,
            "Login Google sedang tidak tersedia. Silakan coba lagi nanti.",
            next_url,
        )

    client_id, _, _ = configuration

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    pending = request.session.get(OAUTH_SESSION_KEY, {})
    pending[state] = {"nonce": nonce, "verifier": verifier, "next": next_url}
    request.session[OAUTH_SESSION_KEY] = dict(list(pending.items())[-MAX_PENDING_STATES:])

    parameters = {
        "client_id": client_id,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return HttpResponseRedirect(f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{urlencode(parameters)}")


def _username_for_email(email):
    User = get_user_model()
    base = slugify(email.partition("@")[0])[:130] or "google-user"
    username = base
    while User.objects.filter(username=username).exists():
        username = f"{base[:130 - 9]}-{uuid.uuid4().hex[:8]}"
    return username


def _get_or_create_user(claims):
    User = get_user_model()
    subject = claims["sub"]
    email = claims["email"].strip()

    linked = GoogleIdentity.objects.select_related("user").filter(subject=subject).first()
    if linked:
        return linked.user

    with transaction.atomic():
        matches = list(User.objects.filter(email__iexact=email).order_by("pk")[:2])
        if len(matches) > 1:
            raise ValueError("More than one account uses this email address.")
        if matches:
            user = matches[0]
        else:
            full_name = (claims.get("name") or "").strip()
            given_name = (claims.get("given_name") or "").strip()
            family_name = (claims.get("family_name") or "").strip()
            if not given_name and full_name:
                given_name, _, remaining = full_name.partition(" ")
                family_name = family_name or remaining
            user = User(
                username=_username_for_email(email),
                email=email,
                first_name=given_name[:150],
                last_name=family_name[:150],
            )
            user.set_unusable_password()
            user.save()

        GoogleIdentity.objects.create(user=user, subject=subject)
    return user


@require_GET
def google_callback(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    configuration = _oauth_configuration()
    if configuration is None:
        return _oauth_error(
            request,
            "Login Google sedang tidak tersedia. Silakan coba lagi nanti.",
        )
    client_id, client_secret, redirect_uri = configuration

    state = request.GET.get("state", "")
    pending = request.session.get(OAUTH_SESSION_KEY, {})
    flow = pending.pop(state, None) if state else None
    request.session[OAUTH_SESSION_KEY] = pending
    if (
        not isinstance(flow, dict)
        or not flow.get("nonce")
        or not flow.get("verifier")
    ):
        return _oauth_error(
            request,
            "Sesi masuk sudah kedaluwarsa. Silakan coba masuk lagi.",
        )

    if request.GET.get("error"):
        return _oauth_error(
            request,
            "Proses masuk Google dibatalkan. Silakan coba lagi.",
            flow.get("next", ""),
        )
    code = request.GET.get("code")
    if not code:
        return _oauth_error(
            request,
            "Google tidak mengirim kode masuk. Silakan coba lagi.",
            flow.get("next", ""),
        )

    try:
        token_response = requests.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": flow["verifier"],
            },
            timeout=10,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        claims = id_token.verify_oauth2_token(
            token_data["id_token"], GoogleRequest(), audience=client_id
        )
    except (requests.RequestException, ValueError, KeyError, TypeError, GoogleAuthError):
        return _oauth_error(
            request,
            "Google tidak dapat memverifikasi akunmu. Silakan coba lagi.",
            flow.get("next", ""),
        )

    if not constant_time_compare(str(claims.get("nonce", "")), flow["nonce"]):
        return _oauth_error(
            request,
            "Verifikasi Google gagal. Silakan coba masuk lagi.",
            flow.get("next", ""),
        )
    if (
        not claims.get("sub")
        or not claims.get("email")
        or claims.get("email_verified") not in (True, "true")
    ):
        return _oauth_error(
            request,
            "Gunakan akun Google dengan alamat email terverifikasi.",
            flow.get("next", ""),
        )

    try:
        user = _get_or_create_user(claims)
    except ValueError:
        return _oauth_error(
            request,
            "Akun ini tidak dapat ditautkan. Silakan hubungi dukungan untuk bantuan.",
            flow.get("next", ""),
        )
    except IntegrityError:
        identity = GoogleIdentity.objects.select_related("user").filter(subject=claims["sub"]).first()
        if identity is None:
            return _oauth_error(
                request,
                "Akun Google tidak dapat ditautkan. Silakan coba lagi.",
                flow.get("next", ""),
            )
        user = identity.user

    if not user.is_active:
        return _oauth_error(
            request,
            "Akun ini tidak aktif. Silakan hubungi dukungan untuk bantuan.",
            flow.get("next", ""),
        )

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.phone_number:
        onboarding_url = reverse("complete_profile")
        next_url = flow.get("next", "")
        if next_url:
            onboarding_url = f"{onboarding_url}?{urlencode({'next': next_url})}"
        return redirect(onboarding_url)
    return redirect(_safe_destination(request, flow.get("next", "")))
