-- Extended airfare observation store.
-- Existing columns are preserved for backward compatibility.
CREATE TABLE IF NOT EXISTS flight_observations (
    id                  BIGSERIAL PRIMARY KEY,
    airline             TEXT        NOT NULL,
    flight_number       TEXT,
    airline_code        TEXT,
    departure_airport_code TEXT,
    departure_airport_name TEXT,
    arrival_airport_code TEXT,
    arrival_airport_name TEXT,
    aircraft_type       TEXT,
    carbon_emission_grams BIGINT,
    carbon_typical_grams BIGINT,
    segment_count       INTEGER,
    segments            JSONB NOT NULL DEFAULT '[]'::jsonb,
    origin              CHAR(3)     NOT NULL,
    destination         CHAR(3)     NOT NULL,
    travel_date         DATE        NOT NULL,
    departure_at        TIMESTAMPTZ,
    arrival_at          TIMESTAMPTZ,
    duration_minutes    INTEGER,
    duration_text       TEXT,
    stops               INTEGER,
    fare_amount         NUMERIC(12, 2),
    currency            TEXT,
    fare_class          TEXT,
    availability        TEXT,
    source              TEXT        NOT NULL,
    scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_payload         JSONB,
    advance_purchase_days INTEGER,
    base_fare           NUMERIC(12, 2),
    taxes               NUMERIC(12, 2),
    fees                NUMERIC(12, 2),
    cleaning_status     TEXT NOT NULL DEFAULT 'raw',
    cleaning_flags      JSONB NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS airline_code TEXT;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS departure_airport_code TEXT;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS departure_airport_name TEXT;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS arrival_airport_code TEXT;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS arrival_airport_name TEXT;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS aircraft_type TEXT;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS carbon_emission_grams BIGINT;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS carbon_typical_grams BIGINT;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS segment_count INTEGER;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS segments JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS advance_purchase_days INTEGER;
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS base_fare NUMERIC(12,2);
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS taxes NUMERIC(12,2);
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS fees NUMERIC(12,2);
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS cleaning_status TEXT NOT NULL DEFAULT 'raw';
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS cleaning_flags JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_flight_obs_route_travel
    ON flight_observations (origin, destination, travel_date, scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_flight_obs_flight_travel
    ON flight_observations (flight_number, travel_date, scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_flight_obs_lead
    ON flight_observations (origin, destination, advance_purchase_days, scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_flight_obs_airline
    ON flight_observations (airline, origin, destination, scraped_at DESC);

CREATE TABLE IF NOT EXISTS route_basket (
    origin CHAR(3) NOT NULL,
    destination CHAR(3) NOT NULL,
    route_weight NUMERIC(12,8) NOT NULL CHECK (route_weight >= 0),
    source TEXT NOT NULL DEFAULT 'configured',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (origin, destination)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    origin CHAR(3),
    destination CHAR(3),
    travel_date DATE,
    advance_purchase_days INTEGER,
    source TEXT,
    status TEXT NOT NULL,
    observations_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_started ON scrape_runs (started_at DESC);
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS scrape_run_id BIGINT REFERENCES scrape_runs(id);
CREATE INDEX IF NOT EXISTS idx_flight_obs_scrape_run ON flight_observations(scrape_run_id);

CREATE TABLE IF NOT EXISTS airfare_index_values (
    id BIGSERIAL PRIMARY KEY,
    index_date DATE NOT NULL,
    frequency TEXT NOT NULL,
    index_name TEXT NOT NULL DEFAULT 'APIx',
    lead_window_days INTEGER,
    index_value NUMERIC(14,6) NOT NULL,
    base_value NUMERIC(14,6) NOT NULL DEFAULT 100,
    route_count INTEGER NOT NULL DEFAULT 0,
    observation_count INTEGER NOT NULL DEFAULT 0,
    methodology TEXT NOT NULL DEFAULT 'Laspeyres-style weighted price relatives',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(index_date, frequency, index_name, lead_window_days)
);
CREATE INDEX IF NOT EXISTS idx_index_values_date ON airfare_index_values(index_date DESC);

CREATE TABLE IF NOT EXISTS dgca_benchmarks (
    reference_month DATE NOT NULL,
    origin CHAR(3),
    destination CHAR(3),
    average_fare NUMERIC(12,2) NOT NULL,
    source TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(reference_month, origin, destination, source)
);

-- SIH cleaning/standardization fields.
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS analysis_fare_amount NUMERIC(12,2);
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS imputation_method TEXT NOT NULL DEFAULT 'none';
ALTER TABLE flight_observations ADD COLUMN IF NOT EXISTS is_outlier BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_flight_obs_analysis_fare
    ON flight_observations(origin, destination, advance_purchase_days, scraped_at DESC, analysis_fare_amount);

CREATE TABLE IF NOT EXISTS flight_segments (
    id BIGSERIAL PRIMARY KEY,
    observation_id BIGINT NOT NULL REFERENCES flight_observations(id) ON DELETE CASCADE,
    segment_number INTEGER NOT NULL,
    from_airport_code TEXT,
    from_airport_name TEXT,
    to_airport_code TEXT,
    to_airport_name TEXT,
    departure_date DATE,
    departure_time TIME,
    arrival_date DATE,
    arrival_time TIME,
    duration_minutes INTEGER,
    aircraft_type TEXT,
    UNIQUE(observation_id, segment_number)
);
CREATE INDEX IF NOT EXISTS idx_flight_segments_observation ON flight_segments(observation_id);
CREATE INDEX IF NOT EXISTS idx_flight_segments_route ON flight_segments(from_airport_code, to_airport_code);
