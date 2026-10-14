from __future__ import annotations

from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from rag import api, auth


class ApiAuthenticationTests(TestCase):
    def setUp(self) -> None:
        self.config = replace(
            auth.settings,
            auth_admin_username="admin",
            auth_admin_password="correct horse battery staple",
            auth_jwt_secret="a-secure-test-key-that-is-at-least-32-bytes",
            auth_cookie_secure=False,
        )
        self.auth_settings_patch = patch.object(auth, "settings", self.config)
        self.api_settings_patch = patch.object(api, "settings", self.config)
        self.auth_settings_patch.start()
        self.api_settings_patch.start()
        self.addCleanup(self.auth_settings_patch.stop)
        self.addCleanup(self.api_settings_patch.stop)
        self.client = TestClient(api.app)

    def test_protected_route_rejects_request_without_login(self) -> None:
        response = self.client.post("/chat", json={"message": "unauthorized"})

        self.assertEqual(response.status_code, 401)

    def test_login_rejects_wrong_password(self) -> None:
        response = self.client.post(
            "/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 401)

    def test_login_sets_http_only_cookie_and_unlocks_protected_routes(self) -> None:
        response = self.client.post(
            "/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        self.assertIn("samesite=strict", response.headers["set-cookie"].lower())
        self.assertTrue(self.client.get("/auth/session").json()["authenticated"])

    def test_logout_clears_cookie_and_protected_routes_reject_again(self) -> None:
        self.client.post(
            "/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        )

        response = self.client.post("/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/auth/session").status_code, 401)
