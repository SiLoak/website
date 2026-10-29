import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from main.security import (
    ajax_login_required,
    collector_required,
    giver_required,
    rate_limit,
)
from pickup.permissions import is_collector, is_giver


def ok_view(request, *args, **kwargs):
    return HttpResponse("ok")


class SecurityTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        User = get_user_model()
        self.giver = User.objects.create_user("giver-sec", password="unused-test-pass")
        self.collector = User.objects.create_user("collector-sec", password="unused-test-pass")
        self.collector.groups.add(Group.objects.get_or_create(name="Collector")[0])

    def request(self, user=None, method="get", path="/x/", **extra):
        request = getattr(self.factory, method)(path, **extra)
        request.user = user or AnonymousUser()
        return request


class RoleHelperTests(SecurityTestCase):
    def test_any_signed_in_user_who_is_not_a_collector_is_a_giver(self):
        self.assertTrue(is_giver(self.giver))
        self.assertFalse(is_collector(self.giver))

    def test_collector_is_not_a_giver(self):
        self.assertTrue(is_collector(self.collector))
        self.assertFalse(is_giver(self.collector))

    def test_anonymous_user_has_no_role(self):
        self.assertFalse(is_giver(AnonymousUser()))
        self.assertFalse(is_collector(AnonymousUser()))


class AjaxLoginRequiredTests(SecurityTestCase):
    def test_anonymous_request_gets_json_401(self):
        response = ajax_login_required(ok_view)(self.request())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(json.loads(response.content)["error"], "Autentikasi diperlukan.")

    def test_signed_in_request_reaches_view(self):
        response = ajax_login_required(ok_view)(self.request(self.giver))
        self.assertEqual(response.content, b"ok")


class RoleRequiredTests(SecurityTestCase):
    def test_giver_required_redirects_anonymous_page_requests_to_login(self):
        response = giver_required()(ok_view)(self.request(path="/pickup/"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/?next=/pickup/", response["Location"])

    def test_giver_required_blocks_collectors_with_403_page(self):
        response = giver_required()(ok_view)(self.request(self.collector))
        self.assertEqual(response.status_code, 403)

    def test_giver_required_allows_givers(self):
        response = giver_required()(ok_view)(self.request(self.giver))
        self.assertEqual(response.content, b"ok")

    def test_collector_required_blocks_givers(self):
        response = collector_required()(ok_view)(self.request(self.giver))
        self.assertEqual(response.status_code, 403)

    def test_collector_required_allows_collectors(self):
        response = collector_required()(ok_view)(self.request(self.collector))
        self.assertEqual(response.content, b"ok")

    def test_json_mode_answers_with_json_errors(self):
        anonymous = giver_required(json=True)(ok_view)(self.request())
        forbidden = giver_required(json=True)(ok_view)(self.request(self.collector))
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(json.loads(forbidden.content)["error"], "Anda tidak memiliki akses.")


class RateLimitTests(SecurityTestCase):
    def limited(self, rate="2/m", scope="test"):
        return rate_limit(scope, rate)(ok_view)

    def test_requests_over_the_limit_get_429_with_retry_after(self):
        view = self.limited()
        for _ in range(2):
            self.assertEqual(view(self.request(self.giver, "post")).status_code, 200)
        blocked = view(self.request(self.giver, "post"))
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked["Retry-After"], "60")
        self.assertIn("Terlalu banyak permintaan", blocked.content.decode())

    def test_get_requests_are_not_limited(self):
        view = self.limited(rate="1/m")
        for _ in range(3):
            self.assertEqual(view(self.request(self.giver)).status_code, 200)

    def test_each_user_has_their_own_bucket(self):
        view = self.limited(rate="1/m")
        self.assertEqual(view(self.request(self.giver, "post")).status_code, 200)
        self.assertEqual(view(self.request(self.collector, "post")).status_code, 200)
        self.assertEqual(view(self.request(self.giver, "post")).status_code, 429)

    def test_anonymous_requests_are_bucketed_by_ip(self):
        view = self.limited(rate="1/m")
        self.assertEqual(view(self.request(method="post", REMOTE_ADDR="10.0.0.1")).status_code, 200)
        self.assertEqual(view(self.request(method="post", REMOTE_ADDR="10.0.0.2")).status_code, 200)
        self.assertEqual(view(self.request(method="post", REMOTE_ADDR="10.0.0.1")).status_code, 429)

    def test_json_requests_get_json_429(self):
        view = self.limited(rate="1/m")
        view(self.request(self.giver, "post"))
        blocked = view(self.request(self.giver, "post", HTTP_ACCEPT="application/json"))
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("error", json.loads(blocked.content))

    def test_scopes_do_not_share_buckets(self):
        first = self.limited(rate="1/m", scope="a")
        second = self.limited(rate="1/m", scope="b")
        self.assertEqual(first(self.request(self.giver, "post")).status_code, 200)
        self.assertEqual(second(self.request(self.giver, "post")).status_code, 200)

    def test_invalid_rate_is_rejected_at_decoration_time(self):
        with self.assertRaises(ValueError):
            rate_limit("bad", "5/week")
