from __future__ import annotations

from typing import Iterable

from psycopg.types.json import Jsonb

from db.connection import connect
from db.models import FlightObservation
from config import Settings

INSERT_SQL = """
INSERT INTO flight_observations (
    airline, flight_number, airline_code, departure_airport_code, departure_airport_name,
    arrival_airport_code, arrival_airport_name, aircraft_type, carbon_emission_grams,
    carbon_typical_grams, segment_count, segments, origin, destination, travel_date,
    departure_at, arrival_at, duration_minutes, duration_text, stops, fare_amount, currency,
    fare_class, availability, source, scraped_at, raw_payload, advance_purchase_days,
    base_fare, taxes, fees, cleaning_status, cleaning_flags, scrape_run_id
) VALUES (
    %(airline)s, %(flight_number)s, %(airline_code)s, %(departure_airport_code)s,
    %(departure_airport_name)s, %(arrival_airport_code)s, %(arrival_airport_name)s,
    %(aircraft_type)s, %(carbon_emission_grams)s, %(carbon_typical_grams)s, %(segment_count)s,
    %(segments)s, %(origin)s, %(destination)s, %(travel_date)s, %(departure_at)s,
    %(arrival_at)s, %(duration_minutes)s, %(duration_text)s, %(stops)s, %(fare_amount)s,
    %(currency)s, %(fare_class)s, %(availability)s, %(source)s, %(scraped_at)s,
    %(raw_payload)s, %(advance_purchase_days)s, %(base_fare)s, %(taxes)s, %(fees)s,
    %(cleaning_status)s, %(cleaning_flags)s, %(scrape_run_id)s
) RETURNING id;
"""


class ObservationPipeline:
    """Insert-only historical store with explicit segment unbundling."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def store(self, observations: Iterable[FlightObservation], scrape_run_id: int | None = None) -> list[int]:
        rows = list(observations)
        if not rows:
            return []

        ids: list[int] = []
        seen_keys: set[tuple] = set()
        with connect(self.settings) as conn:
            with conn.cursor() as cur:
                for item in rows:
                    record = item.to_record()
                    dedupe_key = (
                        record.get("airline"), record.get("flight_number"), record.get("origin"),
                        record.get("destination"), record.get("travel_date"), record.get("departure_at"),
                        record.get("fare_amount"), record.get("advance_purchase_days"),
                    )
                    if scrape_run_id is not None and dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)
                    record["raw_payload"] = Jsonb(record.get("raw_payload") or {})
                    record["segments"] = Jsonb(record.get("segments") or [])
                    record["cleaning_flags"] = Jsonb(record.get("cleaning_flags") or {})
                    record["scrape_run_id"] = scrape_run_id
                    cur.execute(INSERT_SQL, record)
                    fetched = cur.fetchone()
                    if not fetched:
                        continue
                    observation_id = int(fetched["id"])
                    ids.append(observation_id)
                    for segment_no, segment in enumerate(item.segments or [], start=1):
                        cur.execute(
                            """INSERT INTO flight_segments(
                                observation_id,segment_number,from_airport_code,from_airport_name,
                                to_airport_code,to_airport_name,departure_date,departure_time,
                                arrival_date,arrival_time,duration_minutes,aircraft_type
                            ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT(observation_id,segment_number) DO UPDATE SET
                                from_airport_code=EXCLUDED.from_airport_code,
                                from_airport_name=EXCLUDED.from_airport_name,
                                to_airport_code=EXCLUDED.to_airport_code,
                                to_airport_name=EXCLUDED.to_airport_name,
                                departure_date=EXCLUDED.departure_date,
                                departure_time=EXCLUDED.departure_time,
                                arrival_date=EXCLUDED.arrival_date,
                                arrival_time=EXCLUDED.arrival_time,
                                duration_minutes=EXCLUDED.duration_minutes,
                                aircraft_type=EXCLUDED.aircraft_type""",
                            (
                                observation_id, segment_no, segment.get("from_airport_code"),
                                segment.get("from_airport_name"), segment.get("to_airport_code"),
                                segment.get("to_airport_name"), segment.get("departure_date"),
                                _time_value(segment.get("departure_time")), segment.get("arrival_date"),
                                _time_value(segment.get("arrival_time")), segment.get("duration_minutes"),
                                segment.get("aircraft_type"),
                            ),
                        )
            conn.commit()
        return ids


def _time_value(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        from datetime import time
        return time(int(value[0]), int(value[1]), int(value[2]) if len(value) > 2 else 0)
    return value
