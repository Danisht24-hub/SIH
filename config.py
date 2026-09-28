from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def parse_travel_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


@dataclass(frozen=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    database_url: str
    origin: str
    destination: str
    travel_date: date
    currency: str
    request_delay_seconds: float
    scrape_interval_seconds: int

    @property
    def dsn(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def load_settings(origin: str | None = None, destination: str | None = None, travel_date: str | None = None) -> Settings:
    return Settings(
        postgres_host=_env("POSTGRES_HOST", "localhost"),
        postgres_port=int(_env("POSTGRES_PORT", "5432")),
        postgres_db=_env("POSTGRES_DB", "sih_flights"),
        postgres_user=_env("POSTGRES_USER", "postgres"),
        postgres_password=_env("POSTGRES_PASSWORD", "postgres"),
        database_url=_env("DATABASE_URL", ""),
        origin=(origin or _env("ORIGIN", "DEL")).upper(),
        destination=(destination or _env("DESTINATION", "BOM")).upper(),
        travel_date=parse_travel_date(travel_date or _env("TRAVEL_DATE", "2026-10-15")),
        currency=_env("CURRENCY", "INR").upper(),
        request_delay_seconds=float(_env("REQUEST_DELAY_SECONDS", "2")),
        scrape_interval_seconds=int(_env("SCRAPE_INTERVAL_SECONDS", "21600")),
    )
