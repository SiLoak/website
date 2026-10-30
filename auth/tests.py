from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import GoogleIdentity, UserProfile
from .views import OAUTH_SESSION_KEY

User = get_user_model()

OAUTH_SETTINGS = dict(
    GOOGLE_OAUTH_CLIENT_ID="test-client-id",
    GOOGLE_OAUTH_CLIENT_SECRET="test-client-secret",
    GOOGLE_OAUTH_REDIRECT_URI="http://testserver/auth/google/callback/",
)


def _make_user(email="user@example.com", phone="", active=True):
    user = User.objects.create_user(
        username=email.split("@")[0],
        email=email,
        password=None,
    )
    user.is_active = active
    user.set_unusable_password()
    user.save()
    UserProfile.objects.update_or_create(user=user, defaults={"phone_number": phone})
    return user


@override_settings(**OAUTH_SETTINGS)
class GoogleLoginViewTests(TestCase):
    def test_redirects_to_google_authorization_endpoint(self):
        response = self.client.get(reverse("google_login"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("accounts.google.com", response.url)

    def test_safe_next_is_stored_in_session(self):
        self.client.get(reverse("google_login"), {"next": "/waste/new/"})
        pending = self.client.session[OAUTH_SESSION_KEY]
        self.assertEqual(next(iter(pending.values()))["next"], "/waste/new/")

    def test_unsafe_next_is_dropped_from_session(self):
        self.client.get(reverse("google_login"), {"next": "https://attacker.example/"})
        pending = self.client.session[OAUTH_SESSION_KEY]
        self.assertEqual(next(iter(pending.values()))["next"], "")

    def test_authenticated_user_with_phone_is_redirected_to_dashboard(self):
        user = _make_user(phone="+628123456789")
        self.client.force_login(user)
        response = self.client.get(reverse("google_login"))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_authenticated_user_without_phone_is_redirected_to_complete_profile(self):
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse("google_login"))
        self.assertRedirects(response, reverse("complete_profile"), fetch_redirect_response=False)

    def test_post_method_not_allowed(self):
        response = self.client.post(reverse("google_login"))
        self.assertEqual(response.status_code, 405)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="", GOOGLE_OAUTH_CLIENT_SECRET="", GOOGLE_OAUTH_REDIRECT_URI="")
    def test_missing_oauth_config_redirects_to_auth_page(self):
        response = self.client.get(reverse("google_login"))
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_pending_states_capped_at_max(self):
        from auth.views import MAX_PENDING_STATES
        for _ in range(MAX_PENDING_STATES + 3):
            self.client.get(reverse("google_login"))
        pending = self.client.session[OAUTH_SESSION_KEY]
        self.assertLessEqual(len(pending), MAX_PENDING_STATES)


@override_settings(**OAUTH_SETTINGS)
class GoogleCallbackViewTests(TestCase):
    def _set_session_state(self, state, nonce, next_url="", verifier="test-verifier"):
        session = self.client.session
        session[OAUTH_SESSION_KEY] = {
            state: {"nonce": nonce, "verifier": verifier, "next": next_url}
        }
        session.save()

    def _do_callback(self, state="s", nonce="n", next_url="", claims_override=None, error_param=None, no_code=False):
        self._set_session_state(state, nonce, next_url)
        claims = {
            "sub": "google-subject-123",
            "email": "oauth-user@example.com",
            "email_verified": True,
            "name": "OAuth User",
            "nonce": nonce,
        }
        if claims_override:
            claims.update(claims_override)

        token_response = Mock()
        token_response.json.return_value = {"id_token": "verified-test-token"}

        params = {"state": state}
        if error_param:
            params["error"] = error_param
        elif not no_code:
            params["code"] = "test-code"

        with (
            patch("auth.views.requests.post", return_value=token_response),
            patch("auth.views.id_token.verify_oauth2_token", return_value=claims),
            patch("auth.views.GoogleRequest"),
        ):
            return self.client.get(reverse("google_callback"), params)

    def test_new_user_without_phone_redirects_to_complete_profile(self):
        response = self._do_callback(next_url="/waste/new/")
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("complete_profile"), response.url)
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_new_user_complete_profile_url_preserves_safe_next(self):
        response = self._do_callback(next_url="/waste/new/")
        self.assertIn("next=%2Fwaste%2Fnew%2F", response.url)

    def test_new_user_complete_profile_url_with_unsafe_next_still_goes_to_complete_profile(self):
        response = self._do_callback(next_url="https://attacker.example/")
        self.assertIn(reverse("complete_profile"), response.url)
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_existing_user_with_phone_redirects_to_safe_next(self):
        user = _make_user(email="oauth-user@example.com", phone="+628123456789")
        GoogleIdentity.objects.create(user=user, subject="google-subject-123")
        response = self._do_callback(next_url="/waste/new/")
        self.assertRedirects(response, "/waste/new/", fetch_redirect_response=False)

    def test_existing_user_with_phone_and_unsafe_next_redirects_to_dashboard(self):
        user = _make_user(email="oauth-user@example.com", phone="+628123456789")
        GoogleIdentity.objects.create(user=user, subject="google-subject-123")
        response = self._do_callback(next_url="https://attacker.example/")
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_missing_state_redirects_to_auth_page(self):
        response = self.client.get(reverse("google_callback"), {"code": "test-code"})
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_unknown_state_redirects_to_auth_page(self):
        self._set_session_state("real-state", "n")
        response = self.client.get(reverse("google_callback"), {"state": "wrong-state", "code": "x"})
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_error_param_redirects_to_auth_page(self):
        response = self._do_callback(error_param="access_denied")
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_missing_code_redirects_to_auth_page(self):
        response = self._do_callback(no_code=True)
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_nonce_mismatch_redirects_to_auth_page(self):
        self._set_session_state("s", "correct-nonce")
        claims = {
            "sub": "google-subject-123",
            "email": "oauth-user@example.com",
            "email_verified": True,
            "name": "OAuth User",
            "nonce": "wrong-nonce",
        }
        token_response = Mock()
        token_response.json.return_value = {"id_token": "t"}
        with (
            patch("auth.views.requests.post", return_value=token_response),
            patch("auth.views.id_token.verify_oauth2_token", return_value=claims),
            patch("auth.views.GoogleRequest"),
        ):
            response = self.client.get(reverse("google_callback"), {"state": "s", "code": "c"})
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_unverified_email_redirects_to_auth_page(self):
        response = self._do_callback(claims_override={"email_verified": False})
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_missing_email_redirects_to_auth_page(self):
        response = self._do_callback(claims_override={"email": ""})
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_missing_sub_redirects_to_auth_page(self):
        response = self._do_callback(claims_override={"sub": ""})
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_token_exchange_failure_redirects_to_auth_page(self):
        import requests as req
        self._set_session_state("s", "n")
        with patch("auth.views.requests.post", side_effect=req.RequestException("timeout")):
            response = self.client.get(reverse("google_callback"), {"state": "s", "code": "c"})
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_inactive_user_is_rejected(self):
        user = _make_user(email="oauth-user@example.com", active=False)
        GoogleIdentity.objects.create(user=user, subject="google-subject-123")
        response = self._do_callback()
        self.assertFalse(self.client.session.get("_auth_user_id"))
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_duplicate_email_value_error_redirects_to_auth_page(self):
        with patch("auth.views._get_or_create_user", side_effect=ValueError):
            response = self._do_callback()
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_integrity_error_with_recoverable_identity_logs_in(self):
        user = _make_user(email="oauth-user@example.com", phone="+628123456789")
        identity = GoogleIdentity.objects.create(user=user, subject="google-subject-123")
        with patch("auth.views._get_or_create_user", side_effect=IntegrityError):
            response = self._do_callback()
        self.assertTrue(self.client.session.get("_auth_user_id"))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_integrity_error_without_identity_redirects_to_auth_page(self):
        with patch("auth.views._get_or_create_user", side_effect=IntegrityError):
            response = self._do_callback()
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_authenticated_user_is_redirected_to_dashboard(self):
        user = _make_user(phone="+628123456789")
        self.client.force_login(user)
        response = self.client.get(reverse("google_callback"), {"state": "s", "code": "c"})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_state_is_consumed_from_session_after_use(self):
        self._do_callback(state="consume-me", nonce="n")
        pending = self.client.session.get(OAUTH_SESSION_KEY, {})
        self.assertNotIn("consume-me", pending)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="", GOOGLE_OAUTH_CLIENT_SECRET="", GOOGLE_OAUTH_REDIRECT_URI="")
    def test_missing_oauth_config_redirects_to_auth_page(self):
        response = self.client.get(reverse("google_callback"), {"state": "s", "code": "c"})
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_picture_url_updated_on_returning_user(self):
        user = _make_user(email="oauth-user@example.com", phone="+628123456789")
        identity = GoogleIdentity.objects.create(user=user, subject="google-subject-123", picture_url="http://old.example/pic.jpg")
        self._do_callback(claims_override={"picture": "http://new.example/pic.jpg"})
        identity.refresh_from_db()
        self.assertEqual(identity.picture_url, "http://new.example/pic.jpg")

    def test_post_method_not_allowed(self):
        response = self.client.post(reverse("google_callback"))
        self.assertEqual(response.status_code, 405)


class AuthPageViewTests(TestCase):
    def test_anonymous_user_sees_login_page(self):
        response = self.client.get(reverse("auth_page"))
        self.assertEqual(response.status_code, 200)

    def test_safe_next_is_passed_to_template(self):
        response = self.client.get(reverse("auth_page"), {"next": "/waste/new/"})
        self.assertEqual(response.context["next_url"], "/waste/new/")

    def test_unsafe_next_is_dropped_from_template(self):
        response = self.client.get(reverse("auth_page"), {"next": "https://attacker.example/"})
        self.assertEqual(response.context["next_url"], "")

    def test_authenticated_user_with_phone_redirected_to_dashboard(self):
        user = _make_user(phone="+628123456789")
        self.client.force_login(user)
        response = self.client.get(reverse("auth_page"))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_authenticated_user_without_phone_redirected_to_complete_profile(self):
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse("auth_page"))
        self.assertRedirects(response, reverse("complete_profile"), fetch_redirect_response=False)


class CompleteProfileViewTests(TestCase):
    def test_unauthenticated_redirects_to_auth_page(self):
        response = self.client.get(reverse("complete_profile"))
        self.assertRedirects(response, reverse("auth_page"), fetch_redirect_response=False)

    def test_user_with_phone_redirected_to_dashboard(self):
        user = _make_user(phone="+628123456789")
        self.client.force_login(user)
        response = self.client.get(reverse("complete_profile"))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_get_renders_form(self):
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse("complete_profile"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_valid_post_saves_phone_and_redirects(self):
        user = _make_user()
        self.client.force_login(user)
        response = self.client.post(reverse("complete_profile"), {"phone_number": "+628123456789", "next": ""})
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.phone_number, "+628123456789")

    def test_valid_post_with_safe_next_redirects_there(self):
        user = _make_user()
        self.client.force_login(user)
        response = self.client.post(reverse("complete_profile"), {"phone_number": "+628123456789", "next": "/waste/new/"})
        self.assertRedirects(response, "/waste/new/", fetch_redirect_response=False)

    def test_valid_post_with_unsafe_next_redirects_to_dashboard(self):
        user = _make_user()
        self.client.force_login(user)
        response = self.client.post(reverse("complete_profile"), {"phone_number": "+628123456789", "next": "https://attacker.example/"})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_invalid_phone_rerenders_form(self):
        user = _make_user()
        self.client.force_login(user)
        response = self.client.post(reverse("complete_profile"), {"phone_number": "abc", "next": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)


class LogoutViewTests(TestCase):
    def test_post_logs_out_and_redirects(self):
        user = _make_user(phone="+628123456789")
        self.client.force_login(user)
        self.assertTrue(self.client.session.get("_auth_user_id"))
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("landing_page"), fetch_redirect_response=False)
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_get_does_not_log_out(self):
        user = _make_user(phone="+628123456789")
        self.client.force_login(user)
        response = self.client.get(reverse("logout"))
        self.assertRedirects(response, reverse("landing_page"), fetch_redirect_response=False)
        self.assertTrue(self.client.session.get("_auth_user_id"))


class PhoneOnboardingFormTests(TestCase):
    def _get_form(self, phone):
        from .forms import PhoneOnboardingForm
        return PhoneOnboardingForm(data={"phone_number": phone})

    def test_valid_international_phone(self):
        self.assertTrue(self._get_form("+628123456789").is_valid())

    def test_valid_local_phone(self):
        self.assertTrue(self._get_form("08123456789").is_valid())

    def test_invalid_too_short(self):
        self.assertFalse(self._get_form("1234567").is_valid())

    def test_invalid_letters(self):
        self.assertFalse(self._get_form("abcdefghij").is_valid())

    def test_invalid_too_long(self):
        self.assertFalse(self._get_form("+62" + "1" * 16).is_valid())
