from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from config import Settings
from db.models import FlightObservation
from scraper.exceptions import ScraperError


class GoogleFlightsScraper:
    """Acquire current Google Flights results and normalize supported Indian carriers.

    The adapter is source-isolated: acquisition produces normalized
    FlightObservation objects while cleaning, storage and indexing remain downstream.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def search(
        self,
        origin: str,
        destination: str,
        travel_date: date,
    ) -> list[FlightObservation]:
        results = self._search(origin, destination, travel_date, indigo_only=False)
        results = [r for r in results if _is_indigo(r.airline)]
        if not results:
            raise ScraperError(
                f"Google Flights returned route results but no IndiGo (6E) itinerary for "
                f"{origin.upper()}->{destination.upper()} on {travel_date.isoformat()}"
            )
        return results

    def search_all(
        self,
        origin: str,
        destination: str,
        travel_date: date,
    ) -> list[FlightObservation]:
        """Return real listed itineraries for the route, retaining major Indian carriers."""
        return self._search(origin, destination, travel_date, indigo_only=False)

    def _search(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        indigo_only: bool,
    ) -> list[FlightObservation]:
        try:
            from importlib.metadata import version
            installed_version = version("fast-flights")
            from fast_flights import FlightQuery, Passengers, create_query, get_flights
        except ImportError as exc:
            raise ScraperError(
                "Google Flights support requires the fast-flights package. "
                "Run: py -m pip install -r requirements.txt"
            ) from exc

        if tuple(int(part) for part in re.findall(r"\d+", installed_version)[:2]) < (3, 1):
            raise ScraperError(
                f"fast-flights {installed_version} is too old for this project; "
                "install the pinned version with: py -m pip install -r requirements.txt"
            )

        try:
            query = create_query(
                flights=[
                    FlightQuery(
                        date=travel_date.isoformat(),
                        from_airport=origin.upper(),
                        to_airport=destination.upper(),
                        # Do not send the airline restriction to Google.  In practice
                # Google can return an empty result for the 6E server-side
                # filter even when IndiGo operates the route.  Fetch the real
                # route results first and filter the returned offers locally.
                    )
                ],
                trip="one-way",
                seat="economy",
                passengers=Passengers(adults=1),
                currency=self.settings.currency,
                hide_separate_and_self_transfer=True,
            )
            result = get_flights(query)
        except Exception as exc:
            raise ScraperError(
                "Google Flights search failed. "
                "The upstream Google result format or access path may have changed: "
                f"{exc}"
            ) from exc

        flights = list(getattr(result, "flights", result) or [])
        observations: list[FlightObservation] = []
        airlines_seen: set[str] = set()
        for flight in flights:
            airline = _airline_name(flight)
            if airline:
                airlines_seen.add(airline)
            observation = self._to_observation(
                flight, origin.upper(), destination.upper(), travel_date
            )
            if observation is not None and (not indigo_only or _is_indigo(airline)):
                if not indigo_only and not _is_supported_indian_carrier(airline):
                    continue
                observations.append(observation)

        if not observations:
            seen = ", ".join(sorted(airlines_seen)) if airlines_seen else "none"
            scope = "IndiGo (6E)" if indigo_only else "supported Indian carriers"
            raise ScraperError(
                f"Google Flights returned {len(flights)} itinerary result(s), but no {scope} "
                f"itinerary for {origin.upper()}->{destination.upper()} on {travel_date.isoformat()}. "
                f"Airlines seen: {seen}"
            )
        return observations

    def _to_observation(
        self,
        flight: Any,
        origin: str,
        destination: str,
        travel_date: date,
    ) -> FlightObservation | None:
        airline = _airline_name(flight)
        if not airline:
            return None

        legs = _extract_legs(flight)
        first = legs[0] if legs else None
        last = legs[-1] if legs else None
        departure_at = _leg_datetime(first, "departure") if first else None
        arrival_at = _leg_datetime(last, "arrival") if last else None
        if departure_at is None:
            departure_at = _parse_clock(str(getattr(flight, "departure", "") or ""), travel_date)
        if arrival_at is None:
            arrival_at = _parse_clock(str(getattr(flight, "arrival", "") or ""), travel_date)
        if departure_at and arrival_at and arrival_at < departure_at:
            arrival_at += timedelta(days=1)

        leg_durations = [_as_int(_field(leg, "duration")) for leg in legs]
        leg_durations = [x for x in leg_durations if x is not None]
        duration_minutes = sum(leg_durations) if leg_durations else _as_int(getattr(flight, "duration", None))
        if duration_minutes is None and departure_at and arrival_at:
            duration_minutes = max(0, int((arrival_at - departure_at).total_seconds() // 60))
        duration_text = _duration_text(duration_minutes) or str(getattr(flight, "duration", "") or "").strip() or None

        price_raw = getattr(flight, "price", None)
        fare_amount = _parse_amount(price_raw)
        airline_code = str(getattr(flight, "type", "") or getattr(flight, "typ", "") or "").strip() or None
        flight_number = _extract_flight_number(flight)
        segments = [_segment_record(leg) for leg in legs]
        carbon = getattr(flight, "carbon", None)
        carbon_emission = _as_int(_field(carbon, "emission"))
        carbon_typical = _as_int(_field(carbon, "typical_on_route"))
        aircraft = ", ".join(dict.fromkeys(s["aircraft_type"] for s in segments if s.get("aircraft_type"))) or None
        stops = max(len(legs) - 1, 0) if legs else _as_int(getattr(flight, "stops", None))

        return FlightObservation(
            airline=airline,
            airline_code=airline_code,
            flight_number=flight_number,
            origin=origin,
            destination=destination,
            travel_date=travel_date,
            departure_at=departure_at,
            arrival_at=arrival_at,
            duration_minutes=duration_minutes,
            duration_text=duration_text,
            stops=stops,
            fare_amount=fare_amount,
            currency=self.settings.currency,
            fare_class="Economy",
            availability="listed",
            scraped_at=datetime.now(timezone.utc),
            source="google_flights",
            raw_payload=_safe_payload(flight),
            departure_airport_code=_airport_code(_field(first, "from_airport")),
            departure_airport_name=_airport_name(_field(first, "from_airport")),
            arrival_airport_code=_airport_code(_field(last, "to_airport")),
            arrival_airport_name=_airport_name(_field(last, "to_airport")),
            aircraft_type=aircraft,
            carbon_emission_grams=carbon_emission,
            carbon_typical_grams=carbon_typical,
            segment_count=len(legs) if legs else None,
            segments=segments,
        )


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _extract_legs(flight: Any) -> list[Any]:
    value = getattr(flight, "flights", None)
    if value is None and isinstance(flight, dict):
        value = flight.get("flights")
    return list(value or [])


def _simple_dt(value: Any) -> tuple[date | None, tuple[int, int, int] | None]:
    d = _field(value, "date")
    t = _field(value, "time")
    if isinstance(d, (list, tuple)) and len(d) >= 3:
        day = date(int(d[0]), int(d[1]), int(d[2]))
    else:
        day = None
    if isinstance(t, (list, tuple)) and len(t) >= 2:
        return day, (int(t[0]), int(t[1]), int(t[2]) if len(t) > 2 else 0)
    return day, None


def _leg_datetime(leg: Any, field_name: str) -> datetime | None:
    value = _field(leg, field_name)
    day, clock = _simple_dt(value)
    if day is None or clock is None:
        return None
    return datetime(day.year, day.month, day.day, clock[0], clock[1], clock[2], tzinfo=timezone(timedelta(hours=5, minutes=30)))


def _airport_code(airport: Any) -> str | None:
    value = _field(airport, "code")
    return str(value).upper() if value else None


def _airport_name(airport: Any) -> str | None:
    value = _field(airport, "name")
    return str(value) if value else None


def _segment_record(leg: Any) -> dict[str, Any]:
    dep = _field(leg, "departure")
    arr = _field(leg, "arrival")
    _, dep_clock = _simple_dt(dep)
    _, arr_clock = _simple_dt(arr)
    return {
        "from_airport_code": _airport_code(_field(leg, "from_airport")),
        "from_airport_name": _airport_name(_field(leg, "from_airport")),
        "to_airport_code": _airport_code(_field(leg, "to_airport")),
        "to_airport_name": _airport_name(_field(leg, "to_airport")),
        "departure_date": _field(dep, "date"),
        "departure_time": dep_clock,
        "arrival_date": _field(arr, "date"),
        "arrival_time": arr_clock,
        "duration_minutes": _as_int(_field(leg, "duration")),
        "aircraft_type": _field(leg, "plane_type"),
    }


def _duration_text(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _airline_name(flight: Any) -> str:
    """Return the airline label across fast-flights result shapes."""
    for attr in ("name", "airline", "airlines"):
        value = getattr(flight, attr, None)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            text = ", ".join(str(v).strip() for v in value if str(v).strip())
        else:
            text = str(value).strip()
        if text:
            return text
    return ""


def _is_supported_indian_carrier(value: str) -> bool:
    text = value.lower()
    return any(name in text for name in (
        "indigo", "6e", "air india", "air india express", "akasa", "spicejet"
    ))


def _is_indigo(value: str) -> bool:
    text = value.lower()
    return "indigo" in text or text.strip() in {"6e", "6e airlines"}


def _parse_clock(value: str, day: date) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip().replace("\u202f", " ")
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return datetime(
                day.year, day.month, day.day,
                parsed.hour, parsed.minute,
                tzinfo=timezone.utc,
            )
        except ValueError:
            continue
    match = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", cleaned, re.I)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    ampm = (match.group(3) or "").upper()
    if ampm == "PM" and hour < 12:
        hour += 12
    if ampm == "AM" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


def _ahead_days(value: str) -> int:
    match = re.search(r"(\d+)\s*day", value.lower())
    return int(match.group(1)) if match else 0


def _duration_minutes(value: str | None) -> int | None:
    if not value:
        return None
    hours = re.search(r"(\d+)\s*h", value.lower())
    minutes = re.search(r"(\d+)\s*m", value.lower())
    if not hours and not minutes:
        return None
    return (int(hours.group(1)) * 60 if hours else 0) + (int(minutes.group(1)) if minutes else 0)


def _parse_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    match = re.search(r"[0-9][0-9,]*(?:\.[0-9]+)?", str(value))
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except Exception:
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_flight_number(flight: Any) -> str | None:
    for attr in ("flight_number", "flight_numbers"):
        value = getattr(flight, attr, None)
        if value:
            if isinstance(value, (list, tuple)):
                return str(value[0]) if value else None
            return str(value)
    for leg in _extract_legs(flight):
        for attr in ("flight_number", "flight_numbers"):
            value = _field(leg, attr)
            if value:
                if isinstance(value, (list, tuple)):
                    return str(value[0]) if value else None
                return str(value)
    return None


def _safe_payload(flight: Any) -> dict[str, Any]:
    data = getattr(flight, "__dict__", None)
    if isinstance(data, dict):
        return {str(k): _json_safe(v) for k, v in data.items()}
    return {"repr": str(flight)}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    attrs = getattr(value, "__dict__", None)
    if isinstance(attrs, dict):
        return {str(k): _json_safe(v) for k, v in attrs.items()}
    return str(value)
