from __future__ import annotations

import argparse

from config import load_settings
from db.analytics import clean_observations


parser = argparse.ArgumentParser(description="Run the non-destructive SIH cleaning pipeline")
parser.add_argument("--origin")
parser.add_argument("--destination")
args = parser.parse_args()
settings = load_settings()
route = (args.origin.upper(), args.destination.upper()) if args.origin and args.destination else None
count = clean_observations(settings, route)
print(f"Processed {count} observation rows")
