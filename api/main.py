from __future__ import annotations

from datetime import date

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from config import load_settings
from db.connection import connect

app = FastAPI(title="Comparify — Real-time Airfare Price API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
settings = load_settings()


def fetch(sql: str, params: tuple = ()):
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


@app.get("/health")
def health():
    try:
        fetch("SELECT 1")
        return {"status": "ok", "database": "ok"}
    except Exception as exc:
        return {"status": "degraded", "database": "error", "detail": str(exc)}


@app.get("/routes")
def routes(active_only: bool = True):
    rows = fetch(
        "SELECT origin,destination,route_weight,source,active FROM route_basket WHERE (%s=FALSE OR active) ORDER BY origin,destination",
        (active_only,),
    )
    return {"routes": rows}


@app.get("/observations")
def observations(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    travel_date: date | None = None,
    airline: str | None = None,
    lead_days: int | None = None,
    limit: int = Query(100, ge=1, le=5000),
):
    sql = """SELECT id,airline,airline_code,flight_number,origin,destination,travel_date,departure_at,arrival_at,
                    departure_airport_code,departure_airport_name,arrival_airport_code,arrival_airport_name,
                    aircraft_type,carbon_emission_grams,carbon_typical_grams,segment_count,segments,
                    duration_minutes,duration_text,stops,fare_amount,analysis_fare_amount,currency,fare_class,availability,source,
                    scraped_at,advance_purchase_days,base_fare,taxes,fees,cleaning_status,imputation_method,is_outlier
             FROM flight_observations WHERE origin=%s AND destination=%s AND cleaning_status IN ('valid','imputed')"""
    params: list = [origin.upper(), destination.upper()]
    if travel_date:
        sql += " AND travel_date=%s"; params.append(travel_date)
    if airline:
        sql += " AND lower(airline)=lower(%s)"; params.append(airline)
    if lead_days is not None:
        sql += " AND advance_purchase_days=%s"; params.append(lead_days)
    sql += " ORDER BY scraped_at DESC LIMIT %s"; params.append(limit)
    return {"observations": fetch(sql, tuple(params))}


@app.get("/latest")
def latest(origin: str, destination: str, travel_date: date, limit: int = Query(100, ge=1, le=5000)):
    rows = fetch(
        """SELECT DISTINCT ON (COALESCE(flight_number,''), airline, departure_at)
                  id,airline,airline_code,flight_number,origin,destination,travel_date,departure_at,arrival_at,
                  departure_airport_code,departure_airport_name,arrival_airport_code,arrival_airport_name,
                  aircraft_type,carbon_emission_grams,carbon_typical_grams,segment_count,segments,
                  duration_minutes,duration_text,stops,fare_amount,analysis_fare_amount,currency,source,scraped_at,advance_purchase_days
           FROM flight_observations
           WHERE origin=%s AND destination=%s AND travel_date=%s AND cleaning_status IN ('valid','imputed')
           ORDER BY COALESCE(flight_number,''), airline, departure_at, scraped_at DESC
           LIMIT %s""",
        (origin.upper(), destination.upper(), travel_date, limit),
    )
    return {"route": f"{origin.upper()}-{destination.upper()}", "travel_date": travel_date, "observations": rows}


@app.get("/trend")
def trend(origin: str, destination: str, days: int = Query(30, ge=1, le=365), lead_days: int | None = None):
    lead_sql = " AND advance_purchase_days=%s" if lead_days is not None else ""
    params: list = [origin.upper(), destination.upper(), days]
    if lead_days is not None:
        params.append(lead_days)
    rows = fetch(
        f"""SELECT date_trunc('day', scraped_at)::date AS day,
                  COUNT(*) AS observations, MIN(analysis_fare_amount) AS min_fare,
                  percentile_cont(0.5) WITHIN GROUP (ORDER BY analysis_fare_amount) AS median_fare,
                  AVG(analysis_fare_amount) AS avg_fare
           FROM flight_observations
           WHERE origin=%s AND destination=%s AND cleaning_status IN ('valid','imputed')
             AND analysis_fare_amount > 0
             AND scraped_at >= NOW() - (%s || ' days')::interval {lead_sql}
           GROUP BY 1 ORDER BY 1""",
        tuple(params),
    )
    return {"route": f"{origin.upper()}-{destination.upper()}", "trend": rows}


@app.get("/index")
def index(index_date: date | None = None, lead_days: int | None = None, frequency: str | None = None):
    clauses=[]; params=[]
    if index_date:
        clauses.append("index_date=%s"); params.append(index_date)
    if lead_days is not None:
        clauses.append("lead_window_days=%s"); params.append(lead_days)
    if frequency:
        clauses.append("frequency=%s"); params.append(frequency)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = "SELECT * FROM airfare_index_values" + where + " ORDER BY index_date DESC, lead_window_days NULLS FIRST, frequency LIMIT 200"
    return {"index": fetch(sql, tuple(params))}


@app.get("/scrape-runs")
def scrape_runs(limit: int = Query(100, ge=1, le=1000)):
    return {"runs": fetch("SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT %s", (limit,))}


@app.get("/stats")
def stats():
    rows = fetch("""SELECT COUNT(*) AS observations,
                          COUNT(DISTINCT (origin,destination)) AS routes,
                          COUNT(DISTINCT airline) AS airlines,
                          COUNT(*) FILTER (WHERE cleaning_status='valid') AS valid,
                          COUNT(*) FILTER (WHERE cleaning_status='imputed') AS imputed,
                          COUNT(*) FILTER (WHERE is_outlier) AS outliers,
                          MIN(scraped_at) AS first_scrape,
                          MAX(scraped_at) AS last_scrape
                   FROM flight_observations""")
    return rows[0]


@app.get("/dashboard")
def dashboard(lead_days: int = Query(1, ge=1, le=365), days: int = Query(30, ge=1, le=365)):
    return {
        "stats": stats(),
        "routes": routes(True),
        "index": index(lead_days=lead_days),
        "recent_runs": scrape_runs(20),
        "trend": trend("DEL", "BOM", days, lead_days),
    }
