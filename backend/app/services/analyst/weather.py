"""Meteo della gara da Open-Meteo (capitolato del 24/11/2026, modifiche 5 e 13). Solo informazione.

- Coordinate: la citta' dello stadio (venue_city della gara) cercata una volta sola con il geocoding di Open-Meteo,
  nel paese del campionato. Senza citta' o senza risultato nel paese giusto: "n.d." (non si indovina).
- Previsione oraria (temperature_2m, precipitation, wind_speed_10m, weather_code) per le gare del Diario di oggi e
  domani, riletta ogni 6 ore; si mostra l'ora del via e da 2 ore prima a 2 ore dopo.
Open-Meteo e' gratis e senza chiave per uso non commerciale (oltre serve il piano a pagamento).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analyst_capitolato import AnalystVenueGeo, AnalystWeather
from app.services.analyst.lineups import _admitted_upcoming

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REFRESH = timedelta(hours=6)
GEO_RETRY = timedelta(days=30)
HOURLY = ("temperature_2m", "precipitation", "wind_speed_10m", "weather_code")
# il campionato dice "England", il geocoding "United Kingdom"
_COUNTRY_ALIASES = {
    "england": "united kingdom",
    "scotland": "united kingdom",
    "wales": "united kingdom",
    "northern-ireland": "united kingdom",
    "northern ireland": "united kingdom",
    "usa": "united states",
    "south-korea": "south korea",
    "korea republic": "south korea",
    "czech-republic": "czechia",
    "czech republic": "czechia",
}

WEATHER_TEXT = {
    0: ("☀", "sereno"),
    1: ("🌤", "poco nuvoloso"),
    2: ("⛅", "parzialmente nuvoloso"),
    3: ("☁", "nuvoloso"),
    45: ("🌫", "nebbia"),
    48: ("🌫", "nebbia"),
    51: ("🌦", "pioviggine"),
    53: ("🌦", "pioviggine"),
    55: ("🌦", "pioviggine"),
    56: ("🌦", "pioviggine gelata"),
    57: ("🌦", "pioviggine gelata"),
    61: ("🌧", "pioggia debole"),
    63: ("🌧", "pioggia"),
    65: ("🌧", "pioggia forte"),
    66: ("🌧", "pioggia gelata"),
    67: ("🌧", "pioggia gelata"),
    71: ("❄", "neve debole"),
    73: ("❄", "neve"),
    75: ("❄", "neve forte"),
    77: ("❄", "neve"),
    80: ("🌦", "rovesci"),
    81: ("🌧", "rovesci"),
    82: ("🌧", "rovesci forti"),
    85: ("❄", "rovesci di neve"),
    86: ("❄", "rovesci di neve"),
    95: ("⛈", "temporale"),
    96: ("⛈", "temporale con grandine"),
    99: ("⛈", "temporale con grandine"),
}


def clean_city(city: str | None) -> str | None:
    """"Napoli (NA)", "Castellammare di Stabia, Campania" -> la sola citta'."""
    if not city:
        return None
    text = re.sub(r"\(.*?\)", "", str(city)).split(",")[0].split("/")[0]
    text = " ".join(text.split())
    return text or None


def _country(name: str | None) -> str:
    c = (name or "").strip().lower()
    return _COUNTRY_ALIASES.get(c, c)


def pick_place(results: list[dict[str, Any]], country: str | None) -> dict[str, Any] | None:
    want = _country(country)
    for r in results or []:
        if _country(r.get("country")) == want or (want == "united states" and r.get("country_code") == "US"):
            return r
    return None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def geocode(db: Session, http: Any, city: str, country: str, now: datetime) -> AnalystVenueGeo:
    row = db.execute(select(AnalystVenueGeo).where(AnalystVenueGeo.city == city, AnalystVenueGeo.country == country)).scalar_one_or_none()
    if row is not None and (row.status == "ok" or now - _aware(row.looked_up_at) < GEO_RETRY):
        return row
    try:
        res = http.get(GEOCODING_URL, params={"name": city, "count": 10, "language": "en", "format": "json"}, timeout=15)
        results = (res.json().get("results") or []) if res.status_code == 200 else []
    except Exception:  # noqa: BLE001
        logger.warning("diario: geocoding di %s non riuscito", city, exc_info=True)
        results = []
    place = pick_place(results, country)
    if row is None:
        row = AnalystVenueGeo(city=city, country=country, status="nd", looked_up_at=now)
        db.add(row)
    row.looked_up_at = now
    if place:
        row.status, row.latitude, row.longitude = "ok", float(place["latitude"]), float(place["longitude"])
        row.found_name = ", ".join(str(x) for x in (place.get("name"), place.get("admin1"), place.get("country")) if x)[:200]
    else:
        row.status = "nd"
    db.flush()
    return row


def parse_forecast(body: dict[str, Any]) -> dict[str, Any] | None:
    hourly = body.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return None
    out: dict[str, Any] = {}
    for i, t in enumerate(times):
        out[str(t)] = {k: (hourly.get(k) or [None] * len(times))[i] for k in HOURLY}
    return out


def refresh_weather(db: Session, client: Any = None, now: datetime | None = None, *, max_calls: int = 20, http: Any = None) -> dict[str, int]:
    """Giro del Diario: previsione delle gare ammesse di oggi e domani (client API-Football non usato)."""
    now = now or datetime.now(timezone.utc)
    # la stessa gara puo' stare nella scansione di oggi e in quella di domani: una sola previsione per gara
    unique: dict[int, Any] = {}
    for t, f in _admitted_upcoming(db, now):
        unique.setdefault(int(f.id), (t, f))
    matches = list(unique.values())
    out = {"fixtures": len(matches), "calls": 0, "nd": 0}
    if not matches:
        return out
    have = {int(w.fixture_id): w for w in db.execute(select(AnalystWeather).where(AnalystWeather.fixture_id.in_([int(f.id) for _, f in matches]))).scalars()}
    own = http is None
    http = http or httpx.Client()
    try:
        for t, f in sorted(matches, key=lambda m: _aware(m[1].kickoff_at)):
            if out["calls"] >= max_calls:
                break
            w = have.get(int(f.id))
            if w is not None and now - _aware(w.fetched_at) < REFRESH:
                continue
            city = clean_city(f.venue_city)
            geo = geocode(db, http, city, t.country_name or "", now) if city and t.country_name else None
            if w is None:
                w = AnalystWeather(fixture_id=int(f.id), status="nd", fetched_at=now)
                db.add(w)
            w.fetched_at = now
            if geo is None or geo.status != "ok":
                w.status = "nd"
                out["nd"] += 1
                continue
            ko = _aware(f.kickoff_at)
            try:
                res = http.get(
                    FORECAST_URL,
                    params={
                        "latitude": geo.latitude,
                        "longitude": geo.longitude,
                        "hourly": ",".join(HOURLY),
                        "timezone": "UTC",
                        "start_date": (ko - timedelta(hours=3)).date().isoformat(),
                        "end_date": (ko + timedelta(hours=3)).date().isoformat(),
                        "wind_speed_unit": "kmh",
                    },
                    timeout=15,
                )
                hourly = parse_forecast(res.json()) if res.status_code == 200 else None
            except Exception:  # noqa: BLE001
                logger.warning("diario: meteo della gara %s non letto", f.id, exc_info=True)
                hourly = None
            out["calls"] += 1
            w.status = "ok" if hourly else "nd"
            w.latitude, w.longitude, w.hourly_json = geo.latitude, geo.longitude, hourly
        db.commit()
    finally:
        if own:
            http.close()
    return out


def _hour_key(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00")


def weather_view(w: AnalystWeather | None, kickoff: datetime | None) -> dict[str, Any] | None:
    """Meteo al via (ora piena piu' vicina) e da 2 ore prima a 2 ore dopo. None se non c'e' niente."""
    if w is None:
        return None
    fetched = _aware(w.fetched_at)
    base = {"status": w.status, "fetched_at": fetched.isoformat() if fetched else None}
    ko = _aware(kickoff)
    if w.status != "ok" or not w.hourly_json or ko is None:
        return {**base, "status": "nd"}
    start = (ko + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
    hours = []
    for delta in range(-2, 3):
        t = start + timedelta(hours=delta)
        v = (w.hourly_json or {}).get(_hour_key(t))
        if v is None:
            continue
        code = v.get("weather_code")
        icon, text = WEATHER_TEXT.get(int(code), ("·", "")) if code is not None else ("·", "")
        hours.append(
            {
                "at": t.isoformat(),
                "temperature": v.get("temperature_2m"),
                "precipitation": v.get("precipitation"),
                "wind": v.get("wind_speed_10m"),
                "code": code,
                "icon": icon,
                "text": text,
            }
        )
    at_kickoff = next((h for h in hours if h["at"] == start.isoformat()), None)
    if at_kickoff is None:
        return {**base, "status": "nd"}
    return {**base, "kickoff": at_kickoff, "hours": hours}


def weather_for(db: Session, fixture_ids: set[int]) -> dict[int, AnalystWeather]:
    if not fixture_ids:
        return {}
    return {int(w.fixture_id): w for w in db.execute(select(AnalystWeather).where(AnalystWeather.fixture_id.in_(fixture_ids))).scalars()}
