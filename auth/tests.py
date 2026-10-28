from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .views import OAUTH_SESSION_KEY


@override_settings(
    GOOGLE_OAUTH_CLIENT_ID="test-client-id",
    GOOGLE_OAUTH_CLIENT_SECRET="test-client-secret",
    GOOGLE_OAUTH_REDIRECT_URI="http://testserver/auth/google/callback/",
)
class GoogleOAuthRedirectTests(TestCase):
    def callback(self, *, next_url=""):
        state = "test-state"
        nonce = "test-nonce"
        session = self.client.session
        session[OAUTH_SESSION_KEY] = {
            state: {"nonce": nonce, "verifier": "test-verifier", "next": next_url}
        }
        session.save()

        token_response = Mock()
        token_response.json.return_value = {"id_token": "verified-test-token"}
        claims = {
            "sub": "google-subject-123",
            "email": "oauth-user@example.com",
            "email_verified": True,
            "name": "OAuth User",
            "nonce": nonce,
        }
        with (
            patch("auth.views.requests.post", return_value=token_response),
            patch("auth.views.id_token.verify_oauth2_token", return_value=claims),
            patch("auth.views.GoogleRequest"),
        ):
            return self.client.get(
                reverse("google_callback"), {"state": state, "code": "test-code"}
            )

    def test_google_login_carries_only_safe_return_paths_through_oauth_state(self):
        response = self.client.get(
            reverse("google_login"), {"next": "/waste/new/"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("accounts.google.com", response.url)
        pending = self.client.session[OAUTH_SESSION_KEY]
        self.assertEqual(next(iter(pending.values()))["next"], "/waste/new/")

        unsafe_response = self.client.get(
            reverse("google_login"), {"next": "https://attacker.example/"}
        )
        self.assertEqual(unsafe_response.status_code, 302)
        pending = self.client.session[OAUTH_SESSION_KEY]
        self.assertEqual(list(pending.values())[-1]["next"], "")

    def test_callback_redirects_to_dashboard_after_successful_login(self):
        response = self.callback(next_url="/waste/new/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_callback_redirects_to_dashboard_for_external_return_path(self):
        response = self.callback(next_url="https://attacker.example/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))
        self.assertTrue(self.client.session.get("_auth_user_id"))
