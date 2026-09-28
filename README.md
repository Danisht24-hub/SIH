# Comparify — SIH26056 Real-time Airfare Price Index

Comparify is the implementation of the SIH26056 concept: automated domestic-airfare collection, cleaning/standardization, route-wise historical tracking, and a real-time Airfare Price Index (APIx) exposed through REST APIs and an interactive dashboard.

The SIH deck describes the target flow as **Data Collection → Clean & Standardize → Index Calculation → Trend Analysis → Insights**, with PostgreSQL, Celery + Redis, FastAPI, React/TypeScript/Tailwind CSS, Plotly, Docker and Pytest. The implementation in this repository follows that architecture. (SIH deck, page 3).

## Architecture

```text
Airlines / OTAs / DGCA city-pair inputs
                 │
                 ▼
        Source acquisition layer
        Google Flights adapter
                 │
                 ▼
       Raw FlightObservation
                 │
                 ▼
  Unbundle → Filter → Impute → Standardize
                 │
                 ├── flight_observations
                 └── flight_segments
                 │
                 ▼
             PostgreSQL
                 │
        ┌────────┴────────┐
        ▼                 ▼
   APIx engine       FastAPI REST API
        │                 │
        │                 ▼
        │          React + Plotly dashboard
        │
        ▼
 Daily / Weekly / Monthly index

Celery + Redis → scheduled collection
Docker → reproducible services
Pytest → parser/regression tests
```

The SIH diagram explicitly calls for source data, an extraction engine, a scheduler, cleaning/normalization, structured storage, a route-weighted APIx calculation, FastAPI, and a React dashboard. (SIH deck, page 3).

## What is implemented

### 1. Automated data collection

- Google Flights acquisition through the existing `fast-flights` adapter.
- Supported Indian carriers are filtered locally after obtaining route results.
- Five advance-purchase windows: **T+1, T+7, T+15, T+30, T+45**.
- Insert-only historical observations preserve fare changes over time.
- `scrape_runs` records successful and failed collection attempts.
- Celery + Redis provide the production scheduler/worker path.
- The existing CLI scheduler remains available for local debugging.

The SIH concept specifically requires automated, frequent airfare capture because prices change with demand, booking time, season and availability. fileciteturn6file0L21-L27

### 2. Cleaning and standardization

The cleaning pipeline is deliberately non-destructive:

```text
Raw observations
      ↓
Unbundle segments
      ↓
Filter invalid / sold-out / impossible records
      ↓
Impute missing fare only when a route + lead-window median exists
      ↓
Standardize airline / airport / currency / fare-class fields
      ↓
Flag IQR fare outliers (do not silently delete them)
      ↓
Structured analytical fields
```

Every observation retains its original `raw_payload`. Imputation is explicitly recorded in `imputation_method`, and outliers are recorded in `is_outlier` and `cleaning_flags`.

### 3. Structured segment data

The scraper stores the nested itinerary as JSON and also unbundles individual legs into `flight_segments`.

This makes it possible to analyze:

- airport-to-airport legs,
- stops,
- segment duration,
- aircraft type,
- departure/arrival times,
- connecting itineraries.

### 4. Airfare Price Index (APIx)

The SIH architecture shows the index as a weighted current-price/base-price calculation. (SIH deck, page 3).

This implementation therefore uses the corresponding **Laspeyres-style weighted price-relative formulation**:

```text
APIx = Σ [ route_weight × (current_route_price / base_route_price) ] × 100
```

The route price is the cleaned route/lead-window median fare. The base price is the earliest available route/lead-window median in the stored historical series. Route weights are normalized across the active route basket.

Daily, weekly and monthly APIx values are stored in `airfare_index_values`.

> Important: the bundled route weights are provisional equal weights. For a formal statistical/CPI exercise, replace them with the appropriate DGCA passenger-traffic-derived weights. The SIH deck identifies DGCA aviation/passenger statistics as an official reference source. (SIH deck, page 6).

### 5. REST API

FastAPI exposes:

```text
GET /health
GET /routes
GET /observations
GET /latest
GET /trend
GET /index
GET /scrape-runs
GET /stats
GET /dashboard
```

Example:

```text
http://localhost:8000/observations?origin=DEL&destination=BOM&travel_date=2026-10-15
```

### 6. Interactive dashboard

The `frontend/` application uses:

- React
- TypeScript
- Tailwind CSS
- Plotly

It displays:

- observation counts,
- active routes,
- carrier coverage,
- fare trends,
- APIx history,
- route weights,
- selected route and lead window.

This corresponds to the SIH requirement for route-wise visualization and an interactive analytics dashboard. (SIH deck, page 2).

### 7. DGCA benchmark/back-test support

`dgca_benchmark_template.csv` can be populated with an actual permitted DGCA/MoSPI benchmark dataset. `backtest.py` compares the collected route-month series with supplied benchmark values.

No historical benchmark values are fabricated by the repository.

## Project structure

```text
SihSCRAPING/
├── api/
│   └── main.py
├── db/
│   ├── analytics.py
│   ├── connection.py
│   ├── models.py
│   ├── pipeline.py
│   └── schema.sql
├── frontend/
│   ├── src/
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.ts
├── scraper/
│   ├── exceptions.py
│   └── google_flights.py
├── tests/
│   └── test_google_flights.py
├── celery_app.py
├── tasks.py
├── scheduler.py
├── run_scraper.py
├── export_database.py
├── backtest.py
├── load_route_weights.py
├── verify_schema.py
├── route_basket.json
├── route_weights_template.csv
├── dgca_benchmark_template.csv
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Local setup

### Python

```powershell
py -m pip install -r requirements.txt
```

### Docker stack

```powershell
docker compose up -d --build
```

Services:

| Service | URL / port |
|---|---|
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |
| Adminer | `http://localhost:8081` |
| FastAPI | `http://localhost:8000/docs` |
| Dashboard | `http://localhost:3000` |

### Initialize / verify database

```powershell
py run_scraper.py --init-db
py verify_schema.py
```

### Run the cleaning pipeline manually

```powershell
py clean_data.py
py clean_data.py --origin DEL --destination BOM
```

### Single route test

```powershell
py run_scraper.py --origin DEL --destination BOM --date 2026-10-15 --cycles 1
```

### One complete collection cycle

```powershell
py scheduler.py --cycles 1
```

### Continuous local collection

```powershell
py scheduler.py
```

The default interval is six hours (`21600` seconds), matching the intended repeated collection pattern.

### Celery production-style scheduling

Start the services with Docker Compose. The `beat` service schedules `tasks.collect_cycle`; the `worker` service executes it.

```powershell
docker compose logs -f beat worker
```

Do not run the local continuous scheduler and the Celery beat scheduler simultaneously unless you intentionally want two independent collection streams.

## PostgreSQL access

The flight data lives in PostgreSQL, not inside the Git repository.

With Docker:

```powershell
docker exec -it sih_flights_postgres psql -U postgres -d sih_flights
```

Useful queries:

```sql
SELECT COUNT(*) FROM flight_observations;

SELECT airline, origin, destination, travel_date,
       departure_at, arrival_at, fare_amount,
       advance_purchase_days, scraped_at
FROM flight_observations
ORDER BY scraped_at DESC
LIMIT 20;

SELECT index_date, frequency, lead_window_days, index_value, methodology
FROM airfare_index_values
ORDER BY index_date DESC, frequency, lead_window_days;
```

For a managed PostgreSQL provider such as Render, set `DATABASE_URL` in the service environment. The application automatically prefers `DATABASE_URL` when it is present.

## Exporting data

```powershell
py export_database.py
```

Generated files are written to `data/` and are intentionally ignored by Git because real collected data should not be committed to source control.

## Route weights

The current basket is in `route_basket.json`.

For formal weighting, provide a DGCA-derived CSV using the template:

```text
route_weights_template.csv
```

Then load it with:

```powershell
py load_route_weights.py --file route_weights.csv
```

## Testing

```powershell
py -m pytest -q
```

The parser tests cover simple and nested Google Flights result shapes, fare parsing, segment extraction, timestamps, aircraft, stops and carbon fields.

## Source and scope limitations

The SIH deck is a high-level target architecture, not a complete implementation specification. It names airlines/OTAs, DGCA city-pairs, Scrapy/Playwright, Celery/Redis, PostgreSQL, FastAPI and React/TypeScript/Tailwind/Plotly as the intended stack. (SIH deck, page 3).

This repository has a production-ready source-adapter boundary and currently implements the acquisition adapter through `fast-flights`/Google Flights. It does **not** claim to have access to private airline APIs, restricted OTA feeds, or unpublished DGCA data. Where the source does not expose a field, the system stores it as missing rather than inventing a value.

The official-reference section of the SIH deck names MoSPI/NSO, RBI, DGCA and permitted airline/OTA fare sources. (SIH deck, page 6).

## Security / Git

Never commit `.env`, database credentials, production `DATABASE_URL`, or exported live observations. The project `.gitignore` excludes these artifacts.
