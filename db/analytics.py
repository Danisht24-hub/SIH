from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from db.connection import connect
from config import Settings


def upsert_route_basket(settings: Settings, routes: Iterable[dict]) -> None:
    with connect(settings) as conn:
        with conn.cursor() as cur:
            for route in routes:
                cur.execute(
                    """INSERT INTO route_basket(origin,destination,route_weight,source,active)
                       VALUES(%s,%s,%s,%s,TRUE)
                       ON CONFLICT(origin,destination) DO UPDATE SET
                         route_weight=EXCLUDED.route_weight, source=EXCLUDED.source,
                         active=EXCLUDED.active""",
                    (route["origin"].upper(), route["destination"].upper(),
                     route["weight"], route.get("source", "configured")),
                )
        conn.commit()


def route_weights(settings: Settings) -> dict[tuple[str, str], Decimal]:
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT origin,destination,route_weight FROM route_basket WHERE active")
            rows = cur.fetchall()
    weights = {(r["origin"], r["destination"]): Decimal(str(r["route_weight"])) for r in rows}
    total = sum(weights.values(), Decimal("0"))
    if total <= 0:
        raise ValueError("No positive active route weights configured")
    return {k: v / total for k, v in weights.items()}


def clean_observations(settings: Settings, route: tuple[str, str] | None = None) -> int:
    """Normalize, filter and flag observations without deleting raw history.

    The cleaning stages mirror the SIH architecture: filter invalid records,
    retain raw payloads, standardize fields, and create an analysis fare that
    may use a clearly-labelled route/lead-window median only when the source
    fare is missing. Outliers are flagged, not silently deleted.
    """
    where = ""
    params: list = []
    if route:
        where = "WHERE origin=%s AND destination=%s"
        params.extend(route)

    sql = f"""
    WITH route_stats AS (
        SELECT
            origin, destination, advance_purchase_days,
            percentile_cont(0.25) WITHIN GROUP (ORDER BY fare_amount) AS q1,
            percentile_cont(0.75) WITHIN GROUP (ORDER BY fare_amount) AS q3,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY fare_amount) AS median_fare
        FROM flight_observations
        WHERE fare_amount IS NOT NULL AND fare_amount > 0
          AND cleaning_status <> 'excluded_sold_out'
        GROUP BY origin, destination, advance_purchase_days
    )
    UPDATE flight_observations f
    SET
        airline = CASE
            WHEN lower(trim(f.airline)) IN ('6e', 'indigo', 'indigo airlines') THEN 'IndiGo'
            WHEN lower(trim(f.airline)) IN ('air india', 'airindia') THEN 'Air India'
            WHEN lower(trim(f.airline)) IN ('air india express', 'airindia express') THEN 'Air India Express'
            WHEN lower(trim(f.airline)) IN ('akasa', 'akasa air') THEN 'Akasa Air'
            WHEN lower(trim(f.airline)) IN ('spicejet', 'spice jet') THEN 'SpiceJet'
            ELSE trim(f.airline)
        END,
        origin = upper(trim(f.origin)),
        destination = upper(trim(f.destination)),
        currency = upper(coalesce(nullif(trim(f.currency), ''), 'INR')),
        fare_class = initcap(coalesce(nullif(trim(f.fare_class), ''), 'Economy')),
        analysis_fare_amount = CASE
            WHEN f.fare_amount IS NOT NULL AND f.fare_amount > 0 THEN f.fare_amount
            WHEN rs.median_fare IS NOT NULL THEN rs.median_fare
            ELSE NULL
        END,
        imputation_method = CASE
            WHEN f.fare_amount IS NULL OR f.fare_amount <= 0
                THEN CASE WHEN rs.median_fare IS NOT NULL THEN 'route_lead_median' ELSE 'none' END
            ELSE 'none'
        END,
        cleaning_status = CASE
            WHEN f.availability IS NOT NULL AND lower(f.availability) IN ('sold_out','unavailable')
                THEN 'excluded_sold_out'
            WHEN f.fare_amount IS NULL OR f.fare_amount <= 0
                THEN CASE WHEN rs.median_fare IS NOT NULL THEN 'imputed' ELSE 'excluded_missing_or_invalid_fare' END
            WHEN f.departure_at IS NOT NULL AND f.arrival_at IS NOT NULL AND f.arrival_at < f.departure_at
                THEN 'excluded_invalid_time'
            ELSE 'valid'
        END,
        is_outlier = CASE
            WHEN f.fare_amount IS NULL OR f.fare_amount <= 0 OR rs.q1 IS NULL THEN FALSE
            ELSE f.fare_amount < (rs.q1 - 1.5 * (rs.q3-rs.q1))
              OR f.fare_amount > (rs.q3 + 1.5 * (rs.q3-rs.q1))
        END,
        cleaning_flags = jsonb_build_object(
            'fare_missing_or_invalid', (f.fare_amount IS NULL OR f.fare_amount <= 0),
            'sold_out', (f.availability IS NOT NULL AND lower(f.availability) IN ('sold_out','unavailable')),
            'invalid_time', (f.departure_at IS NOT NULL AND f.arrival_at IS NOT NULL AND f.arrival_at < f.departure_at),
            'fare_imputed', (f.fare_amount IS NULL OR f.fare_amount <= 0) AND rs.median_fare IS NOT NULL,
            'outlier', CASE
                WHEN f.fare_amount IS NULL OR f.fare_amount <= 0 OR rs.q1 IS NULL THEN FALSE
                ELSE f.fare_amount < (rs.q1 - 1.5 * (rs.q3-rs.q1))
                  OR f.fare_amount > (rs.q3 + 1.5 * (rs.q3-rs.q1))
            END
        )
    FROM route_stats rs
    WHERE rs.origin=f.origin AND rs.destination=f.destination
      AND rs.advance_purchase_days IS NOT DISTINCT FROM f.advance_purchase_days
      {('AND f.origin=%s AND f.destination=%s' if route else '')}
    """
    # route values appear at the end because they belong to the UPDATE filter.
    if route:
        params = [*params]
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            count = cur.rowcount
        conn.commit()
    return count


def _route_day_medians(settings: Settings, start: date, end: date, lead_days: int | None = None):
    params: list = [start, end]
    lead_sql = ""
    if lead_days is not None:
        lead_sql = " AND advance_purchase_days=%s"
        params.append(lead_days)
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT scraped_at::date AS observation_date,origin,destination,
                           percentile_cont(0.5) WITHIN GROUP (ORDER BY analysis_fare_amount) AS median_fare,
                           COUNT(*) AS observations
                    FROM flight_observations
                    WHERE scraped_at::date BETWEEN %s AND %s
                      AND cleaning_status IN ('valid','imputed')
                      AND analysis_fare_amount>0 {lead_sql}
                    GROUP BY scraped_at::date,origin,destination""",
                params,
            )
            return cur.fetchall()


def _baseline_medians(settings: Settings, lead_days: int | None = None):
    params = []
    lead_sql = ""
    if lead_days is not None:
        lead_sql = " AND advance_purchase_days=%s"
        params.append(lead_days)
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT ON (origin, destination)
                    origin, destination, median_fare, observation_date
                FROM (
                    SELECT origin, destination, scraped_at::date AS observation_date,
                           percentile_cont(0.5) WITHIN GROUP (ORDER BY analysis_fare_amount) AS median_fare
                    FROM flight_observations
                    WHERE cleaning_status IN ('valid','imputed')
                      AND analysis_fare_amount > 0 {lead_sql}
                    GROUP BY origin, destination, scraped_at::date
                ) d
                ORDER BY origin, destination, observation_date
                """,
                params,
            )
            return {
                (r["origin"], r["destination"]): Decimal(str(r["median_fare"]))
                for r in cur.fetchall() if r["median_fare"] is not None
            }


def compute_daily_index(settings: Settings, index_date: date, lead_days: int | None = None) -> dict:
    """Compute APIx using the Laspeyres-style formula shown in the SIH deck.

    APIx = sum(route_weight * current_route_price / base_route_price) * 100.
    """
    weights = route_weights(settings)
    baselines = _baseline_medians(settings, lead_days)
    rows = _route_day_medians(settings, index_date, index_date, lead_days)
    total = 0.0
    used_weight = Decimal("0")
    obs = 0
    route_values = []
    for r in rows:
        key = (r["origin"], r["destination"])
        if key not in weights or key not in baselines or not r["median_fare"]:
            continue
        ratio = float(Decimal(str(r["median_fare"])) / baselines[key])
        if ratio <= 0:
            continue
        total += float(weights[key]) * ratio
        used_weight += weights[key]
        obs += int(r["observations"])
        route_values.append({"origin": key[0], "destination": key[1], "current_fare": float(r["median_fare"]),
                             "base_fare": float(baselines[key]), "price_relative": ratio, "weight": float(weights[key])})
    value = 100.0 * total / float(used_weight) if used_weight > 0 else None
    result = {
        "index_date": index_date.isoformat(), "frequency": "daily", "index_value": value,
        "lead_window_days": lead_days, "route_count": len(route_values), "observation_count": obs,
        "methodology": "Laspeyres-style weighted price relatives", "routes": route_values,
    }
    if value is not None:
        _upsert_index(settings, result)
    return result


def compute_period_index(settings: Settings, period_start: date, period_end: date, frequency: str, lead_days: int | None = None) -> dict:
    daily = []
    current = period_start
    while current <= period_end:
        d = compute_daily_index(settings, current, lead_days)
        if d["index_value"] is not None:
            daily.append(d["index_value"])
        current += timedelta(days=1)
    value = (sum(daily) / len(daily)) if daily else None
    result = {
        "index_date": period_end.isoformat(), "frequency": frequency, "index_value": value,
        "lead_window_days": lead_days, "route_count": None, "observation_count": len(daily),
        "methodology": "Laspeyres-style daily aggregation",
    }
    if value is not None:
        _upsert_index(settings, result)
    return result


def _upsert_index(settings: Settings, result: dict) -> None:
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO airfare_index_values(index_date,frequency,index_name,lead_window_days,index_value,route_count,observation_count,methodology)
                   VALUES(%s,%s,'APIx',%s,%s,%s,%s,%s)
                   ON CONFLICT(index_date,frequency,index_name,lead_window_days) DO UPDATE SET
                     index_value=EXCLUDED.index_value, route_count=EXCLUDED.route_count,
                     observation_count=EXCLUDED.observation_count, methodology=EXCLUDED.methodology, created_at=NOW()""",
                (date.fromisoformat(result["index_date"]), result["frequency"], result["lead_window_days"],
                 result["index_value"], result["route_count"] or 0, result["observation_count"], result["methodology"]),
            )
        conn.commit()


def store_dgca_benchmark(settings: Settings, rows: Iterable[dict]) -> int:
    with connect(settings) as conn:
        with conn.cursor() as cur:
            count = 0
            for row in rows:
                cur.execute(
                    """INSERT INTO dgca_benchmarks(reference_month,origin,destination,average_fare,source)
                       VALUES(%s,%s,%s,%s,%s)
                       ON CONFLICT(reference_month,origin,destination,source) DO UPDATE SET average_fare=EXCLUDED.average_fare, loaded_at=NOW()""",
                    (row["reference_month"], row.get("origin"), row.get("destination"), row["average_fare"], row["source"]),
                )
                count += 1
        conn.commit()
    return count
