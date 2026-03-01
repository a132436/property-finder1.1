import requests
import streamlit as st
from datetime import datetime, timedelta


GOOGLE_MAPS_API_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

# Destinations
BRISTOL_TEMPLE_MEADS = "Bristol Temple Meads Station, Bristol, UK"
LONDON_PADDINGTON = "London Paddington Station, London, UK"

# Use a weekday 8am departure for representative commute times
def _next_weekday_8am() -> int:
    """Returns a Unix timestamp for the next Monday at 8am."""
    now = datetime.now()
    days_ahead = 0 - now.weekday()  # Monday is 0
    if days_ahead <= 0:
        days_ahead += 7
    next_monday = now + timedelta(days=days_ahead)
    monday_8am = next_monday.replace(hour=8, minute=0, second=0, microsecond=0)
    return int(monday_8am.timestamp())


def run_commute_check(listing: dict) -> dict:
    """
    Calculates public transport commute times from the listing's location
    to Bristol Temple Meads and London Paddington.

    Enriches and returns the listing dict with commute data.
    """
    api_key = st.secrets.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        listing["commute_bristol_mins"] = None
        listing["commute_london_mins"] = None
        listing["commute_bristol_text"] = "No API key"
        listing["commute_london_text"] = "No API key"
        listing["_commute_error"] = "GOOGLE_MAPS_API_KEY not in secrets"
        return listing

    # Determine origin — prefer coordinates, fall back to postcode, then full address
    origin = _get_origin(listing)
    if not origin:
        listing["commute_bristol_mins"] = None
        listing["commute_london_mins"] = None
        listing["commute_bristol_text"] = "Location unknown"
        listing["commute_london_text"] = "Location unknown"
        return listing

    # Query both destinations in one API call (saves credits)
    destinations = f"{BRISTOL_TEMPLE_MEADS}|{LONDON_PADDINGTON}"

    params = {
        "origins": origin,
        "destinations": destinations,
        "mode": "transit",
        "departure_time": _next_weekday_8am(),
        "key": api_key,
    }

    try:
        resp = requests.get(GOOGLE_MAPS_API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        listing["_commute_error"] = str(e)
        listing["commute_bristol_mins"] = None
        listing["commute_london_mins"] = None
        listing["commute_bristol_text"] = "API error"
        listing["commute_london_text"] = "API error"
        return listing

    if data.get("status") != "OK":
        listing["_commute_error"] = f"Google Maps API status: {data.get('status')}"
        listing["commute_bristol_mins"] = None
        listing["commute_london_mins"] = None
        listing["commute_bristol_text"] = "Not available"
        listing["commute_london_text"] = "Not available"
        return listing

    rows = data.get("rows", [])
    if not rows:
        listing["commute_bristol_mins"] = None
        listing["commute_london_mins"] = None
        listing["commute_bristol_text"] = "No route data"
        listing["commute_london_text"] = "No route data"
        return listing

    elements = rows[0].get("elements", [{}, {}])

    # Bristol
    bristol_el = elements[0] if len(elements) > 0 else {}
    bristol_mins, bristol_text = _parse_element(bristol_el)
    listing["commute_bristol_mins"] = bristol_mins
    listing["commute_bristol_text"] = bristol_text

    # London
    london_el = elements[1] if len(elements) > 1 else {}
    london_mins, london_text = _parse_element(london_el)
    listing["commute_london_mins"] = london_mins
    listing["commute_london_text"] = london_text

    return listing


def _get_origin(listing: dict) -> str | None:
    """Returns the best available origin string for the Google Maps API."""
    lat = listing.get("latitude")
    lng = listing.get("longitude")
    if lat and lng:
        return f"{lat},{lng}"

    postcode = listing.get("postcode", "").strip()
    if postcode:
        return postcode + ", UK"

    address = listing.get("address", "").strip()
    if address:
        return address + ", UK"

    return None


def _parse_element(element: dict) -> tuple[int | None, str]:
    """
    Parses a Google Maps distance matrix element.
    Returns (minutes, human_readable_text).
    """
    status = element.get("status", "")
    if status != "OK":
        return None, f"No route ({status})"

    duration = element.get("duration", {})
    seconds = duration.get("value")
    text = duration.get("text", "Unknown")

    mins = round(seconds / 60) if seconds else None
    return mins, text
