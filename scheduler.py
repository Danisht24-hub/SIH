from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

from config import load_settings
from db.analytics import clean_observations, compute_daily_index, compute_period_index, upsert_route_basket
from db.connection import connect, init_schema
from db.pipeline import ObservationPipeline
from scraper.google_flights import GoogleFlightsScraper

ROOT = Path(__file__).resolve().parent


def load_routes() -> list[dict]:
    with (ROOT / "route_basket.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)["routes"]


def _mark_run(settings, run_id: int, status: str, count: int = 0, error: str | None = None) -> None:
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scrape_runs SET finished_at=NOW(),status=%s,observations_count=%s,error=%s WHERE id=%s",
                (status, count, error, run_id),
            )
        conn.commit()


def run_cycle(settings, lead_windows: list[int]) -> int:
    routes = load_routes()
    upsert_route_basket(settings, routes)
    init_schema(settings)
    today = date.today()
    total = 0
    scraper = GoogleFlightsScraper(settings)

    for route in routes:
        for lead in lead_windows:
            travel_date = today + timedelta(days=lead)
            run_id = None
            try:
                with connect(settings) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO scrape_runs(origin,destination,travel_date,advance_purchase_days,source,status)
                               VALUES(%s,%s,%s,%s,'google_flights','running') RETURNING id""",
                            (route["origin"], route["destination"], travel_date, lead),
                        )
                        run_id = int(cur.fetchone()["id"])
                    conn.commit()

                observations = scraper.search_all(route["origin"], route["destination"], travel_date)
                for obs in observations:
                    obs.advance_purchase_days = lead
                ids = ObservationPipeline(settings).store(observations, scrape_run_id=run_id)
                clean_observations(settings, (route["origin"], route["destination"]))
                _mark_run(settings, run_id, "success", len(ids))
                total += len(ids)
                print(f"{route['origin']}->{route['destination']} T+{lead}: {len(ids)} observations")
            except Exception as exc:
                print(f"{route['origin']}->{route['destination']} T+{lead}: ERROR {exc}")
                if run_id:
                    try:
                        _mark_run(settings, run_id, "failed", 0, str(exc))
                    except Exception as mark_exc:
                        print(f"Could not update scrape_runs for run {run_id}: {mark_exc}")
            finally:
                if settings.request_delay_seconds > 0:
                    time.sleep(settings.request_delay_seconds)

    for lead in lead_windows:
        try:
            result = compute_daily_index(settings, today, lead)
            print(f"APIx daily T+{lead}: {result['index_value']} ({result['route_count']} routes)")
            weekly = compute_period_index(settings, today - timedelta(days=6), today, "weekly", lead)
            monthly = compute_period_index(settings, today.replace(day=1), today, "monthly", lead)
            print(f"APIx weekly T+{lead}: {weekly['index_value']}")
            print(f"APIx monthly T+{lead}: {monthly['index_value']}")
        except Exception as exc:
            print(f"APIx T+{lead}: ERROR {exc}")
            print("Continuing to the next lead window...")

    print(f"Cycle complete: {total} new observations")
    return total


def main() -> None:
    p = argparse.ArgumentParser(description="Continuous airfare collection scheduler")
    p.add_argument("--interval", type=int, default=None, help="Seconds between complete cycles")
    p.add_argument("--cycles", type=int, default=0, help="0 = continuous")
    p.add_argument("--lead-windows", default="1,7,15,30,45")
    args = p.parse_args()
    settings = load_settings()
    interval = args.interval or max(settings.scrape_interval_seconds, 3600)
    lead_windows = [int(x) for x in args.lead_windows.split(",") if x.strip()]

    cycle = 0
    while True:
        cycle += 1
        print(f"=== collection cycle {cycle} ===")
        run_cycle(settings, lead_windows)
        if args.cycles and cycle >= args.cycles:
            break
        print(f"Sleeping {interval}s")
        time.sleep(interval)


if __name__ == "__main__":
    main()
