from datetime import date
from types import SimpleNamespace

from scraper.google_flights import GoogleFlightsScraper
from config import load_settings


def test_google_flight_is_normalized_to_observation():
    settings = load_settings("DEL", "BOM", "2026-10-15")
    scraper = GoogleFlightsScraper(settings)
    flight = SimpleNamespace(
        name="IndiGo",
        departure="6:15 AM",
        arrival="8:30 AM",
        arrival_time_ahead="",
        duration="2 hr 15 min",
        stops=0,
        price="₹5,432",
    )
    obs = scraper._to_observation(flight, "DEL", "BOM", date(2026, 10, 15))
    assert obs is not None
    assert obs.airline == "IndiGo"
    assert obs.origin == "DEL"
    assert obs.destination == "BOM"
    assert obs.fare_amount == 5432
    assert obs.duration_minutes == 135
    assert obs.source == "google_flights"


def test_non_indigo_result_can_be_normalized_for_multi_carrier_collection():
    settings = load_settings("DEL", "BOM", "2026-10-15")
    scraper = GoogleFlightsScraper(settings)
    flight = SimpleNamespace(name="Air India", departure="6:00 AM", arrival="8:00 AM")
    obs = scraper._to_observation(flight, "DEL", "BOM", date(2026, 10, 15))
    assert obs is not None
    assert obs.airline == "Air India"


def test_airlines_list_result_shape_is_supported():
    settings = load_settings("DEL", "BOM", "2026-10-15")
    scraper = GoogleFlightsScraper(settings)
    flight = SimpleNamespace(
        airlines=["IndiGo"],
        departure="6:15 AM",
        arrival="8:30 AM",
        duration="2 hr 15 min",
        stops=0,
        price="₹5,432",
    )
    obs = scraper._to_observation(flight, "DEL", "BOM", date(2026, 10, 15))
    assert obs is not None
    assert obs.airline == "IndiGo"


class _Obj:
    def __init__(self, **kw): self.__dict__.update(kw)


def test_nested_google_flights_extracts_real_times_airports_duration_and_aircraft():
    from datetime import date
    from scraper.google_flights import GoogleFlightsScraper
    from config import load_settings
    leg = _Obj(
        from_airport=_Obj(code="DEL", name="Indira Gandhi International Airport"),
        to_airport=_Obj(code="BOM", name="Chhatrapati Shivaji Maharaj International Airport Mumbai"),
        departure=_Obj(date=[2026,10,15], time=[9,30]),
        arrival=_Obj(date=[2026,10,15], time=[11,55]),
        duration=145,
        plane_type="Airbus A321neo",
    )
    flight = _Obj(type="6E", airlines=["IndiGo"], price=6474, flights=[leg], carbon=_Obj(emission=87000, typical_on_route=102000))
    obs = GoogleFlightsScraper(load_settings())._to_observation(flight, "DEL", "BOM", date(2026,10,15))
    assert obs.departure_at.hour == 9 and obs.departure_at.minute == 30
    assert obs.departure_at.utcoffset().total_seconds() == 19800
    assert obs.arrival_at.hour == 11 and obs.arrival_at.minute == 55
    assert obs.duration_minutes == 145
    assert obs.departure_airport_code == "DEL"
    assert obs.arrival_airport_code == "BOM"
    assert obs.aircraft_type == "Airbus A321neo"
    assert obs.segment_count == 1
    assert obs.stops == 0
    assert obs.carbon_emission_grams == 87000
    assert obs.segments[0]["departure_time"] == (9, 30, 0)
