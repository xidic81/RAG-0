"""Signed access tokens for the single-admin UI."""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

import jwt

from rag.config import settings

ISSUER = "rag-chatbot"
AUDIENCE = "rag-chatbot-ui"
MINIMUM_SECRET_LENGTH = 32


class AuthConfigurationError(Exception):
    """Raised when required authentication secrets are missing or weak."""


def _configured_secret() -> str:
    secret = settings.auth_jwt_secret
    if len(secret.encode("utf-8")) < MINIMUM_SECRET_LENGTH:
        raise AuthConfigurationError(
            "AUTH_JWT_SECRET must be configured with at least 32 bytes"
        )
    return secret


def create_access_token(username: str, password: str, lifetime_seconds: int) -> str:
    secret = _configured_secret()
    if not settings.auth_admin_username or not settings.auth_admin_password:
        raise AuthConfigurationError(
            "AUTH_ADMIN_USERNAME and AUTH_ADMIN_PASSWORD must be configured"
        )

    username_matches = hmac.compare_digest(
        username.encode("utf-8"), settings.auth_admin_username.encode("utf-8")
    )
    password_matches = hmac.compare_digest(
        password.encode("utf-8"), settings.auth_admin_password.encode("utf-8")
    )
    if not username_matches or not password_matches:
        raise ValueError("Invalid username or password")

    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": settings.auth_admin_username,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(seconds=lifetime_seconds),
        },
        secret,
        algorithm="HS256",
    )


def verify_access_token(token: str) -> str | None:
    secret = _configured_secret()
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None

    subject = claims["sub"]
    return subject if subject == settings.auth_admin_username else None
