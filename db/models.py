from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass
class FlightObservation:
    airline: str
    origin: str
    destination: str
    travel_date: date
    source: str
    scraped_at: datetime
    flight_number: str | None = None
    airline_code: str | None = None
    departure_airport_code: str | None = None
    departure_airport_name: str | None = None
    arrival_airport_code: str | None = None
    arrival_airport_name: str | None = None
    aircraft_type: str | None = None
    carbon_emission_grams: int | None = None
    carbon_typical_grams: int | None = None
    segment_count: int | None = None
    segments: list[dict[str, Any]] = field(default_factory=list)
    departure_at: datetime | None = None
    arrival_at: datetime | None = None
    duration_minutes: int | None = None
    duration_text: str | None = None
    stops: int | None = None
    fare_amount: Decimal | None = None
    currency: str | None = None
    fare_class: str | None = None
    availability: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    advance_purchase_days: int | None = None
    base_fare: Decimal | None = None
    taxes: Decimal | None = None
    fees: Decimal | None = None
    cleaning_status: str = "raw"
    cleaning_flags: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["origin"] = self.origin.upper()
        payload["destination"] = self.destination.upper()
        return payload
