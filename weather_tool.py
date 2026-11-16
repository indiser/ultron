import json
import httpx
from config import LOCATION_FILE

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
       45: "fog", 48: "rime fog",
       51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
       56: "freezing drizzle", 57: "heavy freezing drizzle",
       61: "light rain", 63: "rain", 65: "heavy rain",
       66: "freezing rain", 67: "heavy freezing rain",
       71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
       80: "light showers", 81: "showers", 82: "violent showers",
       85: "snow showers", 86: "heavy snow showers",
       95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail"}


def load_location() -> dict | None:
    if LOCATION_FILE.is_file():
        try:
            return json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_location(loc: dict) -> None:
    LOCATION_FILE.write_text(json.dumps(loc, ensure_ascii=False), encoding="utf-8")


async def geocode(place: str) -> dict:
    parts = [p.strip() for p in place.split(",") if p.strip()]
    if not parts:
        raise ValueError("empty place")
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get("https://geocoding-api.open-meteo.com/v1/search",
                        params={"name": parts[0], "count": 10, "language": "en"})
    r.raise_for_status()
    res = r.json().get("results") or []
    if not res:
        raise ValueError(f"place not found: {place}")
    rest = [p.lower() for p in parts[1:]]

    def hay(x):
        return " ".join(str(x.get(k, "")) for k in ("admin1", "admin2", "country", "country_code")).lower()

    x = next((x for x in res if all(p in hay(x) for p in rest)), res[0])
    name = ", ".join(p for p in (x.get("name"), x.get("admin1"), x.get("country")) if p)
    return {"name": name, "lat": x["latitude"], "lon": x["longitude"],
            "tz": x.get("timezone", ""), "source": "manual"}


async def ip_location() -> dict:
    last = "ip lookup failed"
    async with httpx.AsyncClient(timeout=10) as h:
        try:
            d = (await h.get("http://ip-api.com/json/", params={
                "fields": "status,message,city,regionName,country,lat,lon,timezone"})).json()
            if d.get("status") == "success":
                name = ", ".join(p for p in (d.get("city"), d.get("regionName"), d.get("country")) if p)
                return {"name": name, "lat": d["lat"], "lon": d["lon"],
                        "tz": d.get("timezone", ""), "source": "ip"}
            last = d.get("message", last)
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        try:
            d = (await h.get("https://ipapi.co/json/")).json()
            if d.get("latitude") is not None:
                name = ", ".join(p for p in (d.get("city"), d.get("region"), d.get("country_name")) if p)
                return {"name": name, "lat": d["latitude"], "lon": d["longitude"],
                        "tz": d.get("timezone", ""), "source": "ip"}
            last = d.get("reason", last)
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    raise ValueError(last)


async def get_weather(location: str = "", days: int = 3) -> str:
    try:
        days = max(1, min(int(days or 3), 7))
    except (TypeError, ValueError):
        days = 3
    try:
        if location.strip():
            loc = await geocode(location)
        else:
            loc = await saved_or_detect()
    except Exception as e:
        return f"error: location failed: {e}. Ask the user for a city name."
    params = {
        "latitude": loc["lat"], "longitude": loc["lon"], "timezone": "auto", "forecast_days": days,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as h:
            r = await h.get("https://api.open-meteo.com/v1/forecast", params=params)
        r.raise_for_status()
        d = r.json()
        cur, day = d["current"], d["daily"]
        lines = [
            f"Weather for {loc['name']} (location source: {loc['source']}{', accuracy +-' + str(loc['acc_m']) + ' m' if loc.get('acc_m') else ''})",
            f"Now: {cur['temperature_2m']}C (feels {cur['apparent_temperature']}C), "
            f"{WMO.get(cur['weather_code'], 'code ' + str(cur['weather_code']))}, "
            f"humidity {cur['relative_humidity_2m']}%, wind {cur['wind_speed_10m']} km/h, "
            f"rain {cur['precipitation']} mm",
        ]
        for i, dt in enumerate(day["time"]):
            code = day["weather_code"][i]
            lines.append(
                f"{dt}: {day['temperature_2m_min'][i]} to {day['temperature_2m_max'][i]}C, "
                f"{WMO.get(code, 'code ' + str(code))}, rain {day['precipitation_sum'][i]} mm, "
                f"chance {day['precipitation_probability_max'][i]}%")
        return "\n".join(lines)
    except (KeyError, IndexError) as e:
        return f"error: unexpected weather response: {type(e).__name__}: {e}"
    except Exception as e:
        return f"error: weather request failed: {type(e).__name__}: {e}"

async def reverse(lat: float, lon: float) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as h:
            r = await h.get("https://nominatim.openstreetmap.org/reverse",
                            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 17},
                            headers={"User-Agent": "UltronAgent/1.0"})
        a = r.json().get("address", {})
        area = next((a[k] for k in ("suburb", "neighbourhood", "city_district", "city", "town", "village") if a.get(k)), "")
        parts = [a.get("road", ""), area, a.get("state", ""), a.get("country", "")]
        name = ", ".join(p for p in parts if p)
        if name:
            return name
    except Exception:
        pass
    return f"{lat:.5f}, {lon:.5f}"


async def precise_location() -> dict:
    if os.name != "nt":
        raise ValueError("precise location only works on Windows")
    helper = Path(__file__).parent / "loc_win.ps1"
    try:
        r = await asyncio.to_thread(
            subprocess.run,
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper)],
            capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        raise ValueError("location timed out. Turn on Location services in Windows Settings.")
    except FileNotFoundError:
        raise ValueError("powershell not found in PATH.")
    try:
        d = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        raise ValueError("location helper failed: " + (r.stderr or r.stdout or "no output")[-200:])
    err = d.get("error")
    if err in ("denied", "disabled"):
        raise ValueError("Windows blocked location. Settings > Privacy & security > Location: Location services ON and desktop apps allowed.")
    if err == "unknown":
        raise ValueError("Windows has no position fix yet. Wait a few seconds and retry.")
    if err:
        raise ValueError(str(err))
    acc = d.get("acc")
    acc_m = round(acc) if isinstance(acc, (int, float)) and acc == acc else None
    return {"name": await reverse(d["lat"], d["lon"]), "lat": d["lat"], "lon": d["lon"],
            "tz": "", "source": "windows", "acc_m": acc_m, "ts": time.time()}


async def saved_or_detect() -> dict:
    loc = load_location()
    if loc and loc.get("source") == "windows" and time.time() - loc.get("ts", 0) > 600:
        try:
            loc = await precise_location()
            save_location(loc)
        except Exception:
            pass
    if not loc:
        loc = await ip_location()
        save_location(loc)
    return loc