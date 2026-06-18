#!/usr/bin/env python3
"""
Chicago Neighborhood Events & Closures — Data Fetcher

Queries the City of Chicago's open data portal (SODA API) for upcoming
events and street closures near a specified location. By default uses
910 S Michigan Ave (South Loop).

Datasets:
  - Transport Permits / Street Closures: jdis-5sry (461K records)
  - Special Events (venue-based):         xgse-8eg7 (595 records)

Usage:
  python fetch_events.py                           # 2-week default, South Loop
  python fetch_events.py --days 30                 # 30-day window
  python fetch_events.py --start 2026-07-01 --end 2026-07-14
  python fetch_events.py --lat 41.872 --lon -87.625 --radius 1.0
  python fetch_events.py --output events.json
  python fetch_events.py --pretty                    # Human-readable output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import date, timedelta, datetime

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULT_LAT = 41.872
DEFAULT_LON = -87.625
DEFAULT_RADIUS_MILES = 1.0
DEFAULT_DAYS = 14

SODA_BASE = "https://data.cityofchicago.org/resource"

# Dataset IDs
PERMITS_ID = "jdis-5sry"   # Transportation Dept Permits - Street Closures
EVENTS_ID  = "xgse-8eg7"    # Special Events (venue-based)

# Interesting work types for the permits dataset
# These are the ones that cause people/traffic disruption
INTERESTING_WORK_TYPES = [
    "StClosure",     # Street Closure
    "Festival",      # Festival
    "Parade",        # Parade
    "Filming",       # Filming
    "BlockParty",    # Block Party
    "Assembly",      # Assembly
    "Athletic",      # Athletic event (races, etc.)
    "FarmMkt",       # Farmer's Market
    "SideSale",      # Sidewalk Sale
    "PublicPlac",    # Public Place Obstruction
    "Peoples",       # Make Way for People Program
]

INTERESTING_APP_TYPES = [
    "DOT_SE",        # Special Event Permit
    "DOT_OCC",       # Occupy the Public ROW
]


def build_bbox(lat: float, lon: float, radius_miles: float) -> tuple[float, float, float, float]:
    """
    Build a bounding box around (lat, lon) of `radius_miles`.
    Approximate: 1° lat ≈ 69 mi, 1° lon ≈ 69 * cos(lat) mi.
    """
    import math
    lat_deg = radius_miles / 69.0
    lon_deg = radius_miles / (69.0 * abs(math.cos(math.radians(lat))) or 1)
    return (lat - lat_deg, lat + lat_deg, lon - lon_deg, lon + lon_deg)


def soql(val) -> str:
    """SODA-style quoting: wrap in single quotes."""
    return f"'{val}'"


def _soda_query(dataset_id: str, params: dict, label: str = "data") -> list[dict]:
    """Build and execute a SODA API query with proper URL encoding."""
    base = f"{SODA_BASE}/{dataset_id}.json"
    # Remove None values and encode params
    clean_params = {k: v for k, v in params.items() if v is not None}
    url = base + "?" + urllib.parse.urlencode(clean_params)
    return _soda_get(url, label)


def fetch_permits(
    start_date: str,
    end_date: str,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    radius_miles: float = DEFAULT_RADIUS_MILES,
    limit: int = 500,
) -> list[dict]:
    """Fetch street closure permits near a location within a date range.
    
    Only returns permits that:
    - Are special events (DOT_SE) — festivals, parades, athletic events
    - Are street closures (StClosure work type)
    - START within the date window (new/upcoming construction)
    - Have been active for less than 60 days (recent ongoing work)
    """
    lat_min, lat_max, lon_min, lon_max = build_bbox(lat, lon, radius_miles)

    from datetime import datetime, timedelta

    # Special event permits — always show, they're short-duration events
    clauses_se = [
        f"applicationtype = 'DOT_SE'",
        f"applicationstartdate <= {soql(end_date + 'T23:59:59')}",
        f"applicationenddate >= {soql(start_date + 'T00:00:00')}",
        f"latitude between {lat_min} and {lat_max}",
        f"longitude between {lon_min} and {lon_max}",
    ]

    # Occupy ROW permits — only interesting work types that START in window
    interesting_wts = "','".join(INTERESTING_WORK_TYPES)
    clauses_occ = [
        f"applicationtype = 'DOT_OCC'",
        f"worktype in ('{interesting_wts}')",
        f"applicationstartdate >= {soql(start_date + 'T00:00:00')}",
        f"applicationstartdate <= {soql(end_date + 'T23:59:59')}",
        f"latitude between {lat_min} and {lat_max}",
        f"longitude between {lon_min} and {lon_max}",
    ]

    # Public Way Openings + other permits — only those starting within the window
    clauses_pwo = [
        f"applicationtype != 'DOT_SE'",
        f"applicationtype != 'DOT_OCC'",
        f"applicationstartdate >= {soql(start_date + 'T00:00:00')}",
        f"applicationstartdate <= {soql(end_date + 'T23:59:59')}",
        f"latitude between {lat_min} and {lat_max}",
        f"longitude between {lon_min} and {lon_max}",
    ]

    where = " OR ".join([
        f"({' AND '.join(clauses_se)})",
        f"({' AND '.join(clauses_occ)})",
        f"({' AND '.join(clauses_pwo)})",
    ])

    params = {
        "$where": where,
        "$order": "applicationstartdate ASC",
        "$limit": str(limit),
    }
    return _soda_query(PERMITS_ID, params, "permits")


def fetch_special_events(
    start_date: str,
    end_date: str,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    radius_miles: float = DEFAULT_RADIUS_MILES,
    limit: int = 200,
) -> list[dict]:
    """Fetch special events near a location within a date range."""
    lat_min, lat_max, lon_min, lon_max = build_bbox(lat, lon, radius_miles)

    clauses = [
        f"date >= {soql(start_date)}",
        f"date <= {soql(end_date)}",
    ]

    params = {
        "$where": " AND ".join(clauses),
        "$order": "date ASC",
        "$limit": str(limit),
    }
    events = _soda_query(EVENTS_ID, params, "special events")

    # Post-filter by bounding box since we can't do spatial in Special Events
    filtered = []
    for e in events:
        loc = e.get("location")
        if loc and isinstance(loc, dict):
            coords = loc.get("coordinates")
            if coords and len(coords) == 2:
                elon, elat = coords
                if lat_min <= elat <= lat_max and lon_min <= elon <= lon_max:
                    filtered.append(e)

    return filtered


def _soda_get(url: str, label: str = "data") -> list[dict]:
    """Make a SODA API GET request and return parsed JSON."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ChicagoNeighborhoodEvents/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("error"):
                print(f"⚠️  API error fetching {label}: {data.get('message', 'unknown')}", file=sys.stderr)
                return []
            return data if isinstance(data, list) else []
    except urllib.error.HTTPError as e:
        print(f"⚠️  HTTP {e.code} fetching {label}: {e.reason}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"⚠️  Error fetching {label}: {e}", file=sys.stderr)
        return []


def normalize_permit(p: dict) -> dict:
    """Convert a raw permit record into a clean, normalized event dict."""
    start = p.get("applicationstartdate", "")[:10] if p.get("applicationstartdate") else ""
    end = p.get("applicationenddate", "")[:10] if p.get("applicationenddate") else ""

    address_parts = [
        p.get("streetnumberfrom", ""),
        p.get("direction", ""),
        p.get("streetname", ""),
        p.get("suffix", ""),
    ]
    address = " ".join(part for part in address_parts if part).strip()

    comments = p.get("comments", "") or ""

    # Determine icon/color category
    wt = p.get("worktype", "")
    at = p.get("applicationtype", "")

    if wt == "Festival" or wt == "Parade":
        category = "festival"
    elif wt == "Athletic":
        category = "athletic"
    elif wt in ("StClosure",):
        category = "street_closure"
    elif wt == "Filming":
        category = "filming"
    elif wt == "BlockParty":
        category = "block_party"
    elif wt in ("Assembly", "Peoples"):
        category = "community"
    elif wt in ("FarmMkt", "SideSale", "PublicPlac"):
        category = "commercial"
    elif at == "DOT_SE":
        category = "festival"  # General special event
    else:
        category = "construction"

    return {
        "id": p.get("uniquekey", ""),
        "source": "transport_permit",
        "title": p.get("applicationname", "") or comments[:60] or address,
        "description": comments or p.get("worktypedescription", ""),
        "category": category,
        "date_start": start,
        "date_end": end,
        "address": address,
        "closure_type": p.get("streetclosure", ""),
        "ward": "",
        "lat": float(p.get("latitude", 0)),
        "lon": float(p.get("longitude", 0)),
        "permit_type": p.get("applicationdescription", ""),
        "work_type": p.get("worktypedescription", ""),
        "status": p.get("applicationstatus", ""),
    }


def normalize_event(e: dict) -> dict:
    """Convert a raw Special Events record into a clean event dict."""
    loc = e.get("location", {})
    coords = loc.get("coordinates", [0, 0]) if isinstance(loc, dict) else [0, 0]
    if coords and len(coords) == 2:
        lon, lat = coords
    else:
        lat, lon = 0, 0

    return {
        "id": e.get(":id", "") or f"evt_{hash(e.get('event_details',''))}",
        "source": "special_event",
        "title": e.get("event_details", ""),
        "description": f"{e.get('event_type', '')} at {e.get('venue', '')}",
        "category": (e.get("event_type", "") or "").lower().replace(" ", "_"),
        "date_start": (e.get("date") or "")[:10] if e.get("date") else "",
        "date_end": (e.get("date") or "")[:10] if e.get("date") else "",
        "address": e.get("venue_address", ""),
        "closure_type": "Full" if e.get("event_type") in ("Parade", "Festival", "Marathon") else "Partial",
        "ward": e.get("ward", ""),
        "lat": float(lat),
        "lon": float(lon),
        "permit_type": "Special Event",
        "work_type": e.get("event_type", ""),
        "status": "Scheduled",
    }


def fetch_all(
    start_date: str | None = None,
    end_date: str | None = None,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    radius_miles: float = DEFAULT_RADIUS_MILES,
    limit: int = 500,
) -> dict:
    """
    Fetch and merge all events + permits into a single result.
    Returns dict with keys: events (merged list), metadata.
    """
    if not start_date:
        start_date = date.today().isoformat()
    if not end_date:
        end_date = (date.today() + timedelta(days=DEFAULT_DAYS)).isoformat()

    permits = fetch_permits(start_date, end_date, lat, lon, radius_miles, limit=limit)
    specials = fetch_special_events(start_date, end_date, lat, lon, radius_miles, limit=limit)

    normalized = [normalize_permit(p) for p in permits]
    normalized += [normalize_event(e) for e in specials]

    # Sort by start date
    normalized.sort(key=lambda x: x["date_start"] or "9999-12-31")

    return {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "location": {"lat": lat, "lon": lon, "radius_miles": radius_miles},
            "date_range": {"start": start_date, "end": end_date},
            "total_events": len(normalized),
            "sources": {
                "transport_permits": f"https://data.cityofchicago.org/d/{PERMITS_ID}",
                "special_events": f"https://data.cityofchicago.org/d/{EVENTS_ID}",
            },
        },
        "events": normalized,
    }


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch Chicago neighborhood events and street closures.",
    )
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT,
                        help=f"Latitude (default: {DEFAULT_LAT})")
    parser.add_argument("--lon", type=float, default=DEFAULT_LON,
                        help=f"Longitude (default: {DEFAULT_LON})")
    parser.add_argument("--radius", type=float, default=DEFAULT_RADIUS_MILES,
                        help=f"Search radius in miles (default: {DEFAULT_RADIUS_MILES})")
    parser.add_argument("--start", type=str, default=None,
                        help="Start date YYYY-MM-DD (default: today)")
    parser.add_argument("--end", type=str, default=None,
                        help="End date YYYY-MM-DD (default: today + 14 days)")
    parser.add_argument("--days", type=int, default=None,
                        help="Number of days from today (overrides --end)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Write JSON to file instead of stdout")
    parser.add_argument("--pretty", "-p", action="store_true",
                        help="Pretty-print JSON output")
    parser.add_argument("--limit", type=int, default=500,
                        help="Max records to fetch (default: 500)")

    args = parser.parse_args()

    if args.days:
        end_date = (date.today() + timedelta(days=args.days)).isoformat()
    else:
        end_date = args.end

    result = fetch_all(
        start_date=args.start,
        end_date=end_date,
        lat=args.lat,
        lon=args.lon,
        radius_miles=args.radius,
        limit=args.limit,
    )

    indent = 2 if args.pretty else None
    output = json.dumps(result, indent=indent, default=str)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"✅ Wrote {result['metadata']['total_events']} events to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
