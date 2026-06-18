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

import argparse
import json
import math
import sys
import urllib.request
import urllib.parse
from datetime import date, timedelta, datetime

LAT, LON, RADIUS, DAYS = 41.872, -87.625, 1.0, 14
SODA = "https://data.cityofchicago.org/resource"
PERMITS, EVENTS = "jdis-5sry", "xgse-8eg7"

# ponytail: work types that cause people/traffic disruption
INTERESTING_WTS = [
    "StClosure", "Festival", "Parade", "Filming", "BlockParty",
    "Assembly", "Athletic", "FarmMkt", "SideSale", "PublicPlac", "Peoples",
]


def build_bbox(lat: float, lon: float, radius_miles: float):
    """Bounding box: 1° lat ≈ 69 mi, 1° lon ≈ 69*cos(lat) mi."""
    d = radius_miles / 69.0
    d2 = radius_miles / (69.0 * abs(math.cos(math.radians(lat))) or 1)
    return (lat - d, lat + d, lon - d2, lon + d2)


def q(val):
    """SODA single-quote wrapping."""
    return f"'{val}'"


def soda_get(dataset: str, params: dict, label="data"):
    """Fetch JSON from SODA. Returns [] on error."""
    url = f"{SODA}/{dataset}.json?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})
    req = urllib.request.Request(url, headers={"User-Agent": "ChiEvents/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
            return d if isinstance(d, list) else []
    except Exception as e:
        print(f"soda {label}: {e}", file=sys.stderr)
        return []


def fetch_permits(start, end, lat=LAT, lon=LON, radius=RADIUS, limit=500):
    """Permits near (lat,lon) within date range. Events (DOT_SE) use date overlap;
    everything else must START in the window to exclude ancient construction."""
    lat_min, lat_max, lon_min, lon_max = build_bbox(lat, lon, radius)
    wts = "','".join(INTERESTING_WTS)

    def block(atype, date_filter, extra=None):
        c = [f"applicationtype={q(atype)}"]
        c += [f"applicationstartdate <= {q(end + 'T23:59:59')}"]
        if date_filter == "overlap":
            c += [f"applicationenddate >= {q(start + 'T00:00:00')}"]
        else:
            c += [f"applicationstartdate >= {q(start + 'T00:00:00')}"]
            c += [f"applicationstartdate <= {q(end + 'T23:59:59')}"]
        if extra:
            c.append(extra)
        c += [f"latitude between {lat_min} and {lat_max}"]
        c += [f"longitude between {lon_min} and {lon_max}"]
        return f"({' AND '.join(c)})"

    where = " OR ".join([
        block("DOT_SE", "overlap"),
        block("DOT_OCC", "start", f"worktype in ('{wts}')"),
        f"(applicationtype NOT IN ('DOT_SE','DOT_OCC') AND applicationstartdate >= {q(start+'T00:00:00')} AND applicationstartdate <= {q(end+'T23:59:59')} AND latitude between {lat_min} and {lat_max} AND longitude between {lon_min} and {lon_max})",
    ])

    return soda_get(PERMITS, {"$where": where, "$order": "applicationstartdate ASC", "$limit": str(limit)}, "permits")


def fetch_events(start, end, lat=LAT, lon=LON, radius=RADIUS, limit=200):
    """Special events (venue-based) near location. Post-filters by bbox."""
    lat_min, lat_max, lon_min, lon_max = build_bbox(lat, lon, radius)
    raw = soda_get(EVENTS, {"$where": f"date >= {q(start)} AND date <= {q(end)}", "$order": "date ASC", "$limit": str(limit)}, "events")
    return [e for e in raw
            if isinstance(e.get("location"), dict)
            and len(e["location"].get("coordinates", [])) == 2
            and lat_min <= e["location"]["coordinates"][1] <= lat_max
            and lon_min <= e["location"]["coordinates"][0] <= lon_max]


# ── Normalizers ────────────────────────────────────────────────────

PERMIT_CATS = {
    "Festival": "festival", "Parade": "festival", "Athletic": "athletic",
    "StClosure": "street_closure", "Filming": "filming", "BlockParty": "block_party",
    "Assembly": "community", "Peoples": "community", "FarmMkt": "commercial",
    "SideSale": "commercial", "PublicPlac": "commercial",
}


def normalize_permit(p):
    wt, at = p.get("worktype", ""), p.get("applicationtype", "")
    category = PERMIT_CATS.get(wt) or ("festival" if at == "DOT_SE" else "construction")
    addr = " ".join(filter(None, [p.get("streetnumberfrom"), p.get("direction"), p.get("streetname"), p.get("suffix")]))
    comments = p.get("comments", "") or ""
    return {
        "id": p.get("uniquekey", ""), "source": "transport_permit",
        "title": p.get("applicationname", "") or comments[:60] or addr,
        "description": comments or p.get("worktypedescription", ""),
        "category": category,
        "date_start": (p.get("applicationstartdate") or "")[:10],
        "date_end": (p.get("applicationenddate") or "")[:10],
        "address": addr, "closure_type": p.get("streetclosure", ""), "ward": "",
        "lat": float(p.get("latitude", 0)), "lon": float(p.get("longitude", 0)),
        "permit_type": p.get("applicationdescription", ""), "work_type": p.get("worktypedescription", ""),
        "status": p.get("applicationstatus", ""),
    }


def normalize_event(e):
    loc = e.get("location") or {}
    coords = loc.get("coordinates") if isinstance(loc, dict) else [0, 0]
    lat, lon = float(coords[1]) if len(coords) == 2 else 0, float(coords[0]) if len(coords) == 2 else 0
    et = e.get("event_type", "")
    return {
        "id": e.get(":id", "") or f"evt_{hash(str(e.get('event_details','')))}",
        "source": "special_event", "title": e.get("event_details", ""),
        "description": f"{et} at {e.get('venue', '')}",
        "category": (et or "").lower().replace(" ", "_"),
        "date_start": (e.get("date") or "")[:10],
        "date_end": (e.get("date") or "")[:10],
        "address": e.get("venue_address", ""),
        "closure_type": "Full" if et in ("Parade", "Festival", "Marathon") else "Partial",
        "ward": e.get("ward", ""), "lat": lat, "lon": lon,
        "permit_type": "Special Event", "work_type": et, "status": "Scheduled",
    }


def fetch_all(start_date=None, end_date=None, lat=LAT, lon=LON, radius=RADIUS, limit=500):
    """Merge permits + events, sorted by date."""
    if not start_date:
        start_date = date.today().isoformat()
    if not end_date:
        end_date = (date.today() + timedelta(days=DAYS)).isoformat()
    events = [normalize_permit(p) for p in fetch_permits(start_date, end_date, lat, lon, radius, limit)]
    events += [normalize_event(e) for e in fetch_events(start_date, end_date, lat, lon, radius, limit)]
    events.sort(key=lambda x: x["date_start"] or "9999-12-31")
    return {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "location": {"lat": lat, "lon": lon, "radius_miles": radius},
            "date_range": {"start": start_date, "end": end_date},
            "total_events": len(events),
            "sources": {"transport_permits": f"https://data.cityofchicago.org/d/{PERMITS}", "special_events": f"https://data.cityofchicago.org/d/{EVENTS}"},
        },
        "events": events,
    }


# ── CLI ───────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Fetch Chicago neighborhood events.")
    defaults = [(LAT, "lat", "Latitude"), (LON, "lon", "Longitude"),
                (RADIUS, "radius", "Search radius (miles)")]
    for d, flag, h in defaults:
        p.add_argument(f"--{flag}", type=float, default=d, help=f"{h} (default: {d})")
    p.add_argument("--start", help="Start date YYYY-MM-DD (default: today)")
    p.add_argument("--end", help="End date YYYY-MM-DD (default: today+14)")
    p.add_argument("--days", type=int, help="Override --end: N days from today")
    p.add_argument("-o", "--output", help="Write JSON to file")
    p.add_argument("-p", "--pretty", action="store_true", help="Pretty-print")
    p.add_argument("--limit", type=int, default=500, help="Max records (default: 500)")
    args = p.parse_args()

    end = args.end
    if args.days:
        end = (date.today() + timedelta(days=args.days)).isoformat()

    result = fetch_all(start_date=args.start, end_date=end,
                       lat=args.lat, lon=args.lon, radius=args.radius, limit=args.limit)

    out = json.dumps(result, indent=2 if args.pretty else None, default=str)
    if args.output:
        with open(args.output, "w") as f:
            f.write(out)
        print(f"Wrote {result['metadata']['total_events']} events to {args.output}", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
