from config import load_settings
from db.connection import connect

REQUIRED = {
    "flight_observations": {
        "id", "airline", "airline_code", "flight_number", "origin", "destination", "travel_date",
        "departure_at", "arrival_at", "departure_airport_code", "departure_airport_name",
        "arrival_airport_code", "arrival_airport_name", "aircraft_type", "carbon_emission_grams",
        "carbon_typical_grams", "segment_count", "segments", "duration_minutes", "duration_text",
        "stops", "fare_amount", "analysis_fare_amount", "currency", "fare_class", "availability",
        "source", "scraped_at", "raw_payload", "advance_purchase_days", "base_fare", "taxes", "fees",
        "cleaning_status", "cleaning_flags", "imputation_method", "is_outlier", "scrape_run_id",
    },
    "flight_segments": {"id", "observation_id", "segment_number", "from_airport_code", "to_airport_code"},
}

settings = load_settings()
with connect(settings) as conn:
    with conn.cursor() as cur:
        for table, required in REQUIRED.items():
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", (table,))
            actual = {r["column_name"] for r in cur.fetchall()}
            missing = required - actual
            if missing:
                raise SystemExit(f"{table}: missing columns: {sorted(missing)}")
            print(f"{table}: schema OK ({len(actual)} columns present)")
print("Schema verification OK")
