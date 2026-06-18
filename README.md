# Chicago Neighborhood Events & Closures

Track upcoming events, street closures, festivals, parades, and construction permits near your Chicago neighborhood — powered by the City of Chicago's open data portal.

[![South Loop Screenshot](https://img.shields.io/badge/Chicago-South%20Loop-orange)](#)
[![Data Source](https://img.shields.io/badge/data-SODA%20API-blue)](https://data.cityofchicago.org/)

---

## 🗺️ Live Demo

Open `index.html` in any browser — no build step, no server, no API key needed.

The page queries two City of Chicago datasets directly from the SODA API:

| Dataset | Records | What It Covers |
|---------|---------|----------------|
| [Transport Permits — Street Closures](https://data.cityofchicago.org/d/jdis-5sry) | 461,000+ | Festivals, parades, athletic events, filming, block parties, construction, utility work |
| [Special Events](https://data.cityofchicago.org/d/xgse-8eg7) | 595 | Venue-based events at McCormick Place, Soldier Field, Wintrust Arena, Grant Park, etc. |

### Features

- ✅ **Interactive map** with color-coded markers by event type
- ✅ **Date range filter** with presets (Today, +1 Week, +1 Month)
- ✅ **Category filter chips** to toggle festival/athletic/closure/construction/etc.
- ✅ **Event list** with dates, addresses, and descriptions
- ✅ **Auto-refresh** every 5 minutes
- ✅ **Works offline** after initial load (data is live-fetched each time)
- ✅ **No backend, no build, no API key** — just a static HTML file

---

## 📂 Project Structure

```
chicago-neighborhood-events/
├── index.html          # Single-page web app (Leaflet map + SODA API)
├── fetch_events.py     # Python CLI for programmatic / cron usage
├── README.md           # This file
└── .gitignore
```

---

## 🐍 Python CLI: `fetch_events.py`

For cron jobs, email alerts, data pipelines, or generating static JSON snapshots:

```bash
# Default: South Loop, 2-week window, pretty-printed
python fetch_events.py --pretty

# Custom date range
python fetch_events.py --start 2026-07-01 --end 2026-07-31 --pretty

# 30-day window
python fetch_events.py --days 30

# Write to file
python fetch_events.py --output events.json

# Different location
python fetch_events.py --lat 41.882 --lon -87.629 --radius 0.75

# Pipe to jq
python fetch_events.py | jq '.events[] | {title, date_start, category}'
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--lat` | 41.872 | Latitude (910 S Michigan) |
| `--lon` | -87.625 | Longitude (910 S Michigan) |
| `--radius` | 0.5 | Search radius in miles |
| `--start` | today | Start date (YYYY-MM-DD) |
| `--end` | today+14 | End date (YYYY-MM-DD) |
| `--days` | — | Overrides `--end`: N days from today |
| `--output` / `-o` | stdout | Write JSON to file |
| `--pretty` / `-p` | false | Pretty-print JSON |
| `--limit` | 500 | Max records to fetch |

### JSON Output Format

```json
{
  "metadata": {
    "generated_at": "2026-06-18T12:58:00",
    "location": { "lat": 41.872, "lon": -87.625, "radius_miles": 0.5 },
    "date_range": { "start": "2026-06-18", "end": "2026-07-02" },
    "total_events": 42,
    "sources": {
      "transport_permits": "https://data.cityofchicago.org/d/jdis-5sry",
      "special_events": "https://data.cityofchicago.org/d/xgse-8eg7"
    }
  },
  "events": [
    {
      "source": "transport_permit",
      "title": "Gold Coast Art Fair",
      "description": "The annual Gold Coast Art Fair returns...",
      "category": "festival",
      "date_start": "2026-06-20",
      "date_end": "2026-06-21",
      "address": "300 E JACKSON",
      "closure_type": "Curblane",
      "lat": 41.877,
      "lon": -87.619
    }
  ]
}
```

---

## 🏙️ Customizing for Your Neighborhood

Edit the constants at the top of **either** file:

### In `index.html` (JavaScript)

```javascript
const CONFIG = {
  lat: 41.872,         // Your latitude
  lon: -87.625,        // Your longitude
  zoom: 15,            // Initial map zoom
  radiusMiles: 0.5,    // Search radius
  defaultDays: 14,     // Default date window
};
```

### In `fetch_events.py`

```python
DEFAULT_LAT = 41.872
DEFAULT_LON = -87.625
DEFAULT_RADIUS_MILES = 0.5
DEFAULT_DAYS = 14
```

---

## ☁️ Hosting

This is a **static site** — no server needed.

### GitHub Pages
1. Push to GitHub
2. Go to Settings → Pages → Source: main branch, `/ (root)`
3. Your page is live at `https://<username>.github.io/chicago-neighborhood-events/`

### Any static host
Upload `index.html` anywhere — S3, Netlify, Vercel, Caddy, nginx.

### Cron job (daily email/notification)
```bash
# Run daily at 8am, save to a web-accessible path
0 8 * * * cd /path/to/project && python fetch_events.py --output /var/www/events/data.json
```

---

## 📡 Data Sources

All data is from the **City of Chicago Open Data Portal** ([data.cityofchicago.org](https://data.cityofchicago.org/)), mandated by Executive Order (Dec 2012). No API key, registration, or rate limits for public access.

- **Street Closures Permits**: [jdis-5sry](https://data.cityofchicago.org/d/jdis-5sry)
- **Special Events**: [xgse-8eg7](https://data.cityofchicago.org/d/xgse-8eg7)
- **SODA API Documentation**: [dev.socrata.com](https://dev.socrata.com/)

Built with [Leaflet.js](https://leafletjs.com/) and [OpenStreetMap](https://www.openstreetmap.org/).

---

## 📄 License

MIT — use freely. Data is public domain from the City of Chicago.

---

## 🚀 Deployment to pihole.lan

### Prerequisites
- SSH access to `pihole.lan` (password `g` via sshpass)
- The `getit-homepage` nginx container must be running

### Quick deploy
```bash
./deploy.sh
```

This copies `index.html` to `/home/bill/.docker/getit/html/neighborhood/` on pihole.lan, which is bind-mounted into the `getit-homepage` nginx container at `/usr/share/nginx/html/neighborhood/`.

The page is then served at **http://getit.lan/neighborhood/**

### Updating the getit.lan homepage
The homepage at `getit.lan` (`/home/bill/.docker/getit/html/index.html`) has a card for this service. Edit that file to update the card's icon, description, or URL.

### Infrastructure
| Component | Detail |
|-----------|--------|
| Host | pihole.lan (192.168.0.19) |
| Container | `getit-homepage` (nginx:alpine) |
| Port | 127.0.0.1:3004 |
| Proxy | Caddy at `/etc/caddy/Caddyfile` → `localhost:3004` |
| Bind mount | `/home/bill/.docker/getit/html` → `/usr/share/nginx/html` (read-only) |
| URL | http://getit.lan/neighborhood/ |

### Updating npm deps (if any)
This is a static HTML/JS page — no build step, no npm dependencies.
