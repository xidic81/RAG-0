from __future__ import annotations

from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

import jwt

import rag.auth as auth


class AccessTokenTests(TestCase):
    def setUp(self) -> None:
        self.config = replace(
            auth.settings,
            auth_admin_username="admin",
            auth_admin_password="correct horse battery staple",
            auth_jwt_secret="a-secure-test-key-that-is-at-least-32-bytes",
        )
        self.settings_patch = patch.object(auth, "settings", self.config)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)

    def test_issues_and_verifies_token_for_admin_credentials(self) -> None:
        token = auth.create_access_token("admin", "correct horse battery staple", 1800)

        self.assertEqual(auth.verify_access_token(token), "admin")

    def test_rejects_incorrect_credentials(self) -> None:
        with self.assertRaises(ValueError):
            auth.create_access_token("admin", "incorrect", 1800)

    def test_rejects_modified_token(self) -> None:
        token = auth.create_access_token("admin", "correct horse battery staple", 1800)
        modified_token = token[:-1] + ("a" if token[-1] != "a" else "b")

        self.assertIsNone(auth.verify_access_token(modified_token))

    def test_rejects_expired_token(self) -> None:
        expired = jwt.encode(
            {
                "sub": "admin",
                "iss": auth.ISSUER,
                "aud": auth.AUDIENCE,
                "iat": 1,
                "exp": 2,
            },
            self.config.auth_jwt_secret,
            algorithm="HS256",
        )

        self.assertIsNone(auth.verify_access_token(expired))

    def test_requires_strong_signing_secret(self) -> None:
        with patch.object(auth, "settings", replace(self.config, auth_jwt_secret="short")):
            with self.assertRaises(auth.AuthConfigurationError):
                auth.create_access_token("admin", "correct horse battery staple", 1800)
