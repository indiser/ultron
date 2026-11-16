import math
import httpx
from weather_tool import saved_or_detect, geocode

OSM = {
    "restaurant": "amenity=restaurant", "cafe": "amenity=cafe", "fast_food": "amenity=fast_food",
    "bar": "amenity=bar", "hospital": "amenity=hospital", "pharmacy": "amenity=pharmacy",
    "atm": "amenity=atm", "bank": "amenity=bank", "fuel": "amenity=fuel",
    "hotel": "tourism=hotel", "museum": "tourism=museum", "attraction": "tourism=attraction",
    "park": "leisure=park", "supermarket": "shop=supermarket", "airport": "aeroway=aerodrome",
    "railway_station": "railway=station", "bus_station": "amenity=bus_station",
}
OVERPASS = "https://overpass-api.de/api/interpreter"


def _km(a_lat, a_lon, b_lat, b_lon) -> float:
    p = math.pi / 180
    h = (math.sin((b_lat - a_lat) * p / 2) ** 2
         + math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin((b_lon - a_lon) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(h))


async def _where(near: str) -> dict:
    if near.strip():
        return await geocode(near)
    return await saved_or_detect()


async def find_places(category: str, near: str = "", radius_km: float = 2, limit: int = 8) -> str:
    tag = OSM.get(category)
    if not tag:
        return f"error: unknown category '{category}'. Use one of: {', '.join(OSM)}"
    try:
        loc = await _where(near)
    except Exception as e:
        return f"error: location failed: {e}. Ask the user for a city name."
    try:
        radius_km = max(0.2, min(float(radius_km or 2), 20))
        limit = max(1, min(int(limit or 8), 15))
    except (TypeError, ValueError):
        radius_km, limit = 2, 8
    k, v = tag.split("=")
    q = (f'[out:json][timeout:25];nwr["{k}"="{v}"](around:{int(radius_km * 1000)},{loc["lat"]},{loc["lon"]});'
         f'out center tags 80;')
    try:
        async with httpx.AsyncClient(timeout=40) as h:
            r = await h.post(OVERPASS, data={"data": q}, headers={"User-Agent": "UltronAgent/1.0"})
        if r.status_code in (429, 504):
            return "error: map server busy. Tell the user to retry in a minute."
        r.raise_for_status()
        els = r.json().get("elements", [])
    except Exception as e:
        return f"error: places request failed: {type(e).__name__}: {e}"
    rows = []
    for e in els:
        t = e.get("tags", {})
        name = t.get("name")
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if not name or lat is None or lon is None:
            continue
        addr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street"), t.get("addr:city")) if x)
        extra = ", ".join(f"{lbl} {t[key]}" for lbl, key in
                          (("cuisine", "cuisine"), ("hours", "opening_hours"), ("phone", "phone")) if t.get(key))
        rows.append((_km(loc["lat"], loc["lon"], lat, lon), name, addr, extra))
    if not rows:
        return f"No {category} found within {radius_km} km of {loc['name']} in map data. Try a bigger radius."
    rows.sort()
    lines = [f"{category} near {loc['name']} (location source: {loc['source']}), within {radius_km} km. "
             f"Source OpenStreetMap, no ratings."]
    for i, (d, name, addr, extra) in enumerate(rows[:limit], 1):
        lines.append(f"{i}. {name}, {d:.1f} km" + (f", {addr}" if addr else "") + (f", {extra}" if extra else ""))
    return "\n".join(lines)