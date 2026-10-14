from __future__ import annotations

from unittest import TestCase

from rag.config import load_settings


class PostgresSettingsTests(TestCase):
    def test_uses_railway_private_url_when_postgres_dsn_is_unset(self) -> None:
        settings = load_settings({"DATABASE_PRIVATE_URL": "postgresql://railway/db"})

        self.assertEqual(settings.postgres_dsn, "postgresql://railway/db")

    def test_postgres_dsn_takes_precedence_over_railway_private_url(self) -> None:
        settings = load_settings(
            {
                "POSTGRES_DSN": "postgresql://configured/db",
                "DATABASE_PRIVATE_URL": "postgresql://railway/db",
            }
        )

        self.assertEqual(settings.postgres_dsn, "postgresql://configured/db")
