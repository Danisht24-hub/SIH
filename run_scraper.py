from __future__ import annotations

import argparse
import json
import time

from config import load_settings
from db.connection import connect, init_schema
from db.analytics import clean_observations
from db.pipeline import ObservationPipeline
from scraper.exceptions import ScraperError
from scraper.google_flights import GoogleFlightsScraper


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect real Google Flights observations and store them in PostgreSQL."
    )
    parser.add_argument("--origin", default=None, help="IATA origin, e.g. DEL")
    parser.add_argument("--destination", default=None, help="IATA destination, e.g. BOM")
    parser.add_argument("--date", dest="travel_date", default=None, help="Travel date YYYY-MM-DD")
    parser.add_argument("--init-db", action="store_true", help="Create/update PostgreSQL schema")
    parser.add_argument("--print-only", action="store_true", help="Print observations without inserting")
    parser.add_argument("--interval", type=int, default=None, help="Seconds between repeated cycles")
    parser.add_argument("--cycles", type=int, default=1, help="Number of cycles; 0 = continuous")
    args = parser.parse_args()

    settings = load_settings(args.origin, args.destination, args.travel_date)
    init_schema(settings)
    if args.init_db:
        print(f"Initialized schema in database {settings.postgres_db}")
        return

    interval = args.interval if args.interval is not None else settings.scrape_interval_seconds
    cycle = 0
    while True:
        cycle += 1
        print(f"--- scrape cycle {cycle} ---")
        print("Fetching live Google Flights results and filtering supported Indian carriers")
        flights = GoogleFlightsScraper(settings).search_all(
            settings.origin, settings.destination, settings.travel_date
        )
        print(
            f"Parsed {len(flights)} real offers for {settings.origin}->{settings.destination} "
            f"on {settings.travel_date} via google_flights"
        )

        if args.print_only:
            for flight in flights:
                print(json.dumps(flight.to_record(), default=str, indent=2))
        else:
            ids = ObservationPipeline(settings).store(flights)
            clean_observations(settings, (settings.origin, settings.destination))
            print(f"Inserted {len(ids)} new observation rows (ids {ids[:8]}{'...' if len(ids) > 8 else ''})")
            if ids:
                with connect(settings) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) AS n FROM flight_observations WHERE id = ANY(%s)", (ids,))
                        verified = int(cur.fetchone()["n"])
                print(f"PostgreSQL verification: {verified}/{len(ids)} inserted row(s) confirmed")
                if verified != len(ids):
                    raise ScraperError(f"PostgreSQL verification failed: expected {len(ids)}, confirmed {verified}")

        if args.cycles and cycle >= args.cycles:
            break
        print(f"Waiting {interval}s before the next scrape cycle")
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except ScraperError as exc:
        raise SystemExit(str(exc)) from exc
    except Exception as exc:
        raise SystemExit(f"Scraper failed: {exc}") from exc
