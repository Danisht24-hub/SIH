# Data exports

This directory is the portable data layer for the SIH airfare project.

Run `py export_database.py` after scraping to create:

- `database_snapshot.sql` — PostgreSQL dump containing schema and collected tables.
- `flight_observations.csv` — tabular observation export.
- `flight_observations.json` — full observation export including normalized segments and raw payload.

Google Flights result data is source-dependent. The project stores the itinerary total fare and the nested segment fields that the source actually returns. Base fare, taxes, convenience fees, and flight numbers remain NULL when Google does not expose them; no values are fabricated.
