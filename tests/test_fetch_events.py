"""
Unit tests for chicago-neighborhood-events data pipeline.

Covers the pure-logic surface of fetch_events.py without network:
  - build_bbox: geodesic bounding-box math
  - normalize_permit: work-type -> category mapping, address assembly
  - normalize_event: special-event normalization, closure_type rules
  - fetch_all: merge + date-sort + metadata

Network fetchers are mocked so tests run offline in CI.
"""
import pytest

from fetch_events import (
    build_bbox,
    normalize_permit,
    normalize_event,
    fetch_all,
    soda_get,
    PERMIT_CATS,
)


# ── build_bbox ───────────────────────────────────────────────────────────

def test_build_bbox_contains_center():
    lat, lon, r = 41.872, -87.625, 1.0
    lat_min, lat_max, lon_min, lon_max = build_bbox(lat, lon, r)
    assert lat_min < lat < lat_max
    assert lon_min < lon < lon_max
    # ~1° lat ≈ 69 mi, so 1 mi radius gives ~±0.0145°
    assert lat_max - lat_min == pytest.approx(2 * r / 69.0, abs=1e-3)
    # lon span widens by 1/cos(lat)
    import math
    expected_lon_span = 2 * r / (69.0 * math.cos(math.radians(lat)))
    assert lon_max - lon_min == pytest.approx(expected_lon_span, rel=0.01)


def test_build_bbox_zero_radius():
    assert build_bbox(10.0, 20.0, 0.0) == (10.0, 10.0, 20.0, 20.0)


def test_build_bbox_at_equator_lon_span_equals_lat_span():
    lat_min, lat_max, lon_min, lon_max = build_bbox(0.0, 0.0, 1.0)
    assert lat_max - lat_min == pytest.approx(lon_max - lon_min, rel=1e-6)


# ── normalize_permit ─────────────────────────────────────────────────────

def test_normalize_permit_festival_category():
    p = {
        "worktype": "Festival", "applicationtype": "DOT_OCC",
        "streetnumberfrom": "100", "direction": "E", "streetname": "Jackson",
        "suffix": "Blvd", "comments": "Music fest", "uniquekey": "K-1",
        "applicationname": "Lollapalooza",
        "applicationstartdate": "2026-07-20T00:00:00", "applicationenddate": "2026-07-22T00:00:00",
        "latitude": "41.877", "longitude": "-87.621",
    }
    out = normalize_permit(p)
    assert out["category"] == "festival"
    assert out["title"] == "Lollapalooza"
    assert out["date_start"] == "2026-07-20"
    assert out["date_end"] == "2026-07-22"
    assert out["address"] == "100 E Jackson Blvd"
    assert out["source"] == "transport_permit"
    assert out["lat"] == pytest.approx(41.877)


def test_normalize_permit_unknown_wt_defaults_construction():
    p = {"worktype": "WaterMain", "applicationtype": "DOT_OCC", "comments": ""}
    out = normalize_permit(p)
    assert out["category"] == "construction"


def test_normalize_permit_dot_se_is_festival_by_default():
    p = {"worktype": "", "applicationtype": "DOT_SE"}
    out = normalize_permit(p)
    assert out["category"] == "festival"


def test_normalize_permit_title_falls_back_to_comment_then_address():
    # no applicationname, has comment -> comment truncated
    p = {"worktype": "StClosure", "applicationtype": "DOT_OCC",
         "comments": "C" * 100, "streetname": "State"}
    out = normalize_permit(p)
    assert out["title"] == "C" * 60
    # neither -> address
    p2 = {"worktype": "Parade", "applicationtype": "DOT_OCC", "comments": "",
          "streetname": "Madison"}
    assert normalize_permit(p2)["title"] == "Madison"


def test_normalize_permit_missing_coords_default_zero():
    out = normalize_permit({"worktype": "Parade", "applicationtype": "DOT_OCC"})
    assert out["lat"] == 0.0
    assert out["lon"] == 0.0


def test_every_interesting_worktype_has_a_category():
    # every worktype the fetcher treats as interesting maps to a category
    from fetch_events import INTERESTING_WTS
    for wt in INTERESTING_WTS:
        assert wt in PERMIT_CATS


# ── normalize_event ──────────────────────────────────────────────────────

def test_normalize_event_full_closure_for_parade():
    e = {
        "event_details": "St Patrick's Day Parade",
        "event_type": "Parade", "venue": "Downtown",
        "date": "2026-03-14T00:00:00",
        "location": {"coordinates": [-87.625, 41.872]},
        "ward": "2", "venue_address": "Michigan Ave",
    }
    out = normalize_event(e)
    assert out["closure_type"] == "Full"
    assert out["category"] == "parade"
    assert out["lat"] == pytest.approx(41.872)
    assert out["lon"] == pytest.approx(-87.625)
    assert out["source"] == "special_event"


def test_normalize_event_partial_closure_otherwise():
    e = {"event_type": "Concert", "location": {"coordinates": [1.0, 2.0]}}
    out = normalize_event(e)
    assert out["closure_type"] == "Partial"


def test_normalize_event_missing_location_defaults_zero():
    out = normalize_event({"event_type": "Concert"})
    assert out["lat"] == 0.0
    assert out["lon"] == 0.0


def test_normalize_event_category_lowercases_and_underscores():
    out = normalize_event({"event_type": "Block Party", "location": {"coordinates": [0, 0]}})
    assert out["category"] == "block_party"


# ── fetch_all (merge + sort) ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def offline_soda(monkeypatch):
    """Replace the network fetcher with canned data so tests never hit the API."""
    canned_permits = [
        {"uniquekey": "P1", "applicationtype": "DOT_OCC", "worktype": "Festival",
         "applicationstartdate": "2026-07-21T00:00:00",
         "applicationenddate": "2026-07-21T00:00:00",
         "streetname": "State", "comments": "", "latitude": "41.87", "longitude": "-87.62"},
    ]
    canned_events = [
        {"event_details": "Later", "event_type": "Concert", "date": "2026-07-23T00:00:00",
         "location": {"coordinates": [-87.62, 41.87]}},
        {"event_details": "Earlier", "event_type": "Parade", "date": "2026-07-20T00:00:00",
         "location": {"coordinates": [-87.62, 41.87]}},
    ]
    monkeypatch.setattr("fetch_events.soda_get", lambda ds, params, label="data":
                        (canned_permits if ds == "jdis-5sry" else canned_events))


def test_fetch_all_merges_and_sorts_by_date(offline_soda):
    result = fetch_all(start_date="2026-07-20", end_date="2026-07-25",
                       lat=41.87, lon=-87.62, radius=1.0)
    events = result["events"]
    # 1 permit + 2 events, sorted ascending by date_start
    assert len(events) == 3
    dates = [e["date_start"] for e in events]
    assert dates == sorted(dates)
    assert dates[0] == "2026-07-20"
    assert dates[-1] == "2026-07-23"


def test_fetch_all_metadata_counts_and_sources(offline_soda):
    result = fetch_all(start_date="2026-07-20", end_date="2026-07-25",
                       lat=41.87, lon=-87.62, radius=1.0)
    assert result["metadata"]["total_events"] == 3
    assert result["metadata"]["date_range"] == {"start": "2026-07-20", "end": "2026-07-25"}
    assert "transport_permits" in result["metadata"]["sources"]
    assert "special_events" in result["metadata"]["sources"]
