import argparse
import csv
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONTAINER = os.getenv("POSTGRES_CONTAINER", "sih_flights_postgres")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "sih_flights")


def run(cmd, output=None):
    with open(output, "wb") if output else subprocess.PIPE as f:
        p = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
    if p.returncode != 0:
        err = p.stderr.decode(errors="replace")
        raise SystemExit(f"Command failed: {' '.join(cmd)}\n{err}")


def main():
    DATA.mkdir(exist_ok=True)
    sql = DATA / "database_snapshot.sql"
    csv_path = DATA / "flight_observations.csv"
    json_path = DATA / "flight_observations.json"

    print("Exporting PostgreSQL database...")
    run(["docker", "exec", CONTAINER, "pg_dump", "-U", DB_USER, "-d", DB_NAME, "--clean", "--if-exists"], sql)

    print("Exporting flight observations as CSV...")
    run(["docker", "exec", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME, "-c", "\\COPY flight_observations TO STDOUT WITH CSV HEADER"], csv_path)

    print("Exporting flight observations as JSON...")
    query = "SELECT row_to_json(t) FROM (SELECT * FROM flight_observations ORDER BY id) t;"
    raw = subprocess.run(["docker", "exec", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME, "-At", "-c", query], capture_output=True)
    if raw.returncode != 0:
        raise SystemExit(raw.stderr.decode(errors="replace"))
    rows = [json.loads(line) for line in raw.stdout.decode().splitlines() if line.strip()]
    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    print(f"Done. Files written to {DATA}")
    print(f"  {sql.name}")
    print(f"  {csv_path.name}")
    print(f"  {json_path.name}")
    print(f"  Observations exported: {len(rows)}")
    print("  Snapshot contains schema + route basket + scrape runs + observations + index + benchmarks")

if __name__ == "__main__":
    main()
