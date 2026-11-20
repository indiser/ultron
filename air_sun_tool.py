"""air_quality + sun_times for Ultron. Both read-only, both free.

uv add astral          (pure Python, sun and moon maths, runs offline)
uv add tzdata          (only if Windows says "No time zone found")

air_quality: Open-Meteo Air Quality API. Free, no key, non-commercial use, CC BY 4.0.
             Data is MODELLED by CAMS (Copernicus), not a street sensor.
sun_times:   astral, no network. Only the location lookup may use the network.
Location logic is the same as get_weather: argument (one-shot, not saved), else saved location, else IP.
"""
import datetime as dt

import httpx
from astral import LocationInfo, moon
from astral.sun import sun

from weather_tool import geocode, ip_location, load_location, save_location

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
BANDS = [(50, "good"), (100, "moderate"), (150, "unhealthy for sensitive groups"), (200, "unhealthy"),
         (300, "very unhealthy"), (10 ** 9, "hazardous")]
NOTE = ("(modelled by CAMS via Open-Meteo, not a street sensor. US AQI scale. "
        "Indian apps use the CPCB scale, so numbers differ.)")


def _now(tz):
    return dt.datetime.now(tz)


def _tz(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name) if name else dt.datetime.now().astimezone().tzinfo
    except Exception:                                   # Windows without tzdata
        return dt.datetime.now().astimezone().tzinfo


async def _where(location):
    if (location or "").strip():
        return await geocode(location.strip())
    loc = load_location()
    if not loc:
        loc = await ip_location()
        save_location(loc)
    return loc


def _head(loc):
    return f"{loc['name']} (location source: {loc.get('source', '?')})"


def _band(v):
    return next(name for top, name in BANDS if v <= top)


def _num(v, unit=""):
    return "n/a" if v is None else f"{v:.0f}{unit}"


# ------------------------------------------------------------- air quality
async def air_quality(location: str = "", **_) -> str:
    try:
        loc = await _where(location)
    except Exception as e:
        return f"error: location failed: {e}. Ask the user for a city name."
    params = {"latitude": loc["lat"], "longitude": loc["lon"], "timezone": "auto", "forecast_days": 2,
              "current": "us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide",
              "hourly": "us_aqi"}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(AQ_URL, params=params)
            r.raise_for_status()
            d = r.json()
        cur = d["current"]
    except httpx.HTTPStatusError as e:
        why = ""
        try:
            why = " " + str(e.response.json().get("reason", ""))[:120]
        except Exception:
            pass
        return f"error: air quality service answered HTTP {e.response.status_code}.{why}"
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return f"error: air quality request failed: {type(e).__name__}"

    aqi = cur.get("us_aqi")
    out = [f"Air quality for {_head(loc)}, timezone {d.get('timezone', loc.get('tz', '?'))}"]
    now = f"Now ({cur.get('time', '?').replace('T', ' ')}): "
    if aqi is None:
        out.append(now + "no AQI value for this place right now")
    else:
        out.append(now + f"US AQI {aqi:.0f} ({_band(aqi)}). PM2.5 {_num(cur.get('pm2_5'))}, PM10 {_num(cur.get('pm10'))}, "
                         f"ozone {_num(cur.get('ozone'))}, NO2 {_num(cur.get('nitrogen_dioxide'))}, "
                         f"SO2 {_num(cur.get('sulphur_dioxide'))}, CO {_num(cur.get('carbon_monoxide'))} (ug/m3)")

    h = d.get("hourly") or {}
    by_day = {}
    for t, v in zip(h.get("time", []), h.get("us_aqi", [])):
        if v is not None:
            by_day.setdefault(t[:10], []).append((t[11:16], v))
    for label, day in zip(("Today", "Tomorrow"), sorted(by_day)[:2]):
        rows = by_day[day]
        worst, best = max(rows, key=lambda x: x[1]), min(rows, key=lambda x: x[1])
        out.append(f"{label} ({day}): worst {worst[1]:.0f} at {worst[0]}, best {best[1]:.0f} at {best[0]}")
    out.append(NOTE)
    return "\n".join(out)


# --------------------------------------------------------------- sun times
def _hm(delta):
    m = int(delta.total_seconds() // 60)
    return f"{m // 60}h {m % 60:02d}m"


def _moon(p):
    for top, name in [(1, "new moon"), (6, "waxing crescent"), (8, "first quarter"), (13, "waxing gibbous"),
                      (15, "full moon"), (20, "waning gibbous"), (22, "last quarter"), (27, "waning crescent")]:
        if p < top:
            return name
    return "new moon"


async def sun_times(location: str = "", days=2, **_) -> str:
    try:
        n = min(7, max(1, int(days)))
    except (TypeError, ValueError):
        n = 2
    try:
        loc = await _where(location)
    except Exception as e:
        return f"error: location failed: {e}. Ask the user for a city name."
    tz = _tz(loc.get("tz"))
    obs = LocationInfo(loc["name"], "", str(loc.get("tz") or ""), loc["lat"], loc["lon"]).observer
    now = _now(tz)
    out = [f"Sun for {_head(loc)}, timezone {loc.get('tz') or 'system'}"]
    for i in range(n):
        day = now.date() + dt.timedelta(days=i)
        try:
            s = sun(obs, date=day, tzinfo=tz)
        except ValueError:
            out.append(f"{day:%a %Y-%m-%d}: the sun does not rise or set on this date at this latitude")
            continue
        out.append(f"{day:%a %Y-%m-%d}: sunrise {s['sunrise']:%H:%M}, sunset {s['sunset']:%H:%M}, "
                   f"daylight {_hm(s['sunset'] - s['sunrise'])}, first light {s['dawn']:%H:%M}, last light {s['dusk']:%H:%M}")
        if i == 0:
            if now < s["sunrise"]:
                out.append(f"Now {now:%H:%M}: sun rises in {_hm(s['sunrise'] - now)}")
            elif now < s["sunset"]:
                out.append(f"Now {now:%H:%M}: sun is up, sunset in {_hm(s['sunset'] - now)}")
            else:
                out.append(f"Now {now:%H:%M}: sun has set for today")
            out.append(f"Moon today: {_moon(moon.phase(day))}")
    return "\n".join(out)