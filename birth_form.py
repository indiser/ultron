import secrets
import threading
import webbrowser
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from flask import Flask, jsonify, render_template_string, request
from werkzeug.serving import make_server

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"

PAGE = """
<!doctype html>
<meta charset="utf-8">
<title>Birth details</title>
<style>
  body{font-family:system-ui;max-width:460px;margin:40px auto;padding:0 16px}
  label{display:block;margin-top:14px;font-weight:600}
  input,button{width:100%;padding:8px;margin-top:4px;box-sizing:border-box}
  .row{display:flex;gap:8px}.row button{width:auto}
  .opt{display:block;font-weight:400;margin-top:6px}
  .opt input{width:auto}
  #msg{margin-top:14px;color:#b00}
</style>
<h2>Birth details</h2>
<label>Date of birth<input type="date" id="date" required></label>
<label>Time of birth (local, 24h)<input type="time" id="time" required></label>
<label>Place of birth
  <div class="row">
    <input id="q" placeholder="e.g. Kolkata">
    <button type="button" onclick="search()">Search</button>
  </div>
</label>
<div id="results"></div>
<button type="button" id="go" style="margin-top:18px" onclick="submitForm()">Submit</button>
<div id="msg"></div>
<script>
const TOKEN = "{{ token }}";
let places = [];
async function search(){
  const q = document.getElementById("q").value.trim();
  if(!q) return;
  const r = await fetch("/search?q=" + encodeURIComponent(q) + "&t=" + TOKEN);
  places = await r.json();
  const box = document.getElementById("results");
  box.innerHTML = places.length ? "" : "No match. Try another spelling.";
  places.forEach((p, i) => {
    box.insertAdjacentHTML("beforeend",
      `<label class="opt"><input type="radio" name="place" value="${i}"> ${p.label}</label>`);
  });
}
async function submitForm(){
  const msg = document.getElementById("msg");
  const sel = document.querySelector("input[name=place]:checked");
  const date = document.getElementById("date").value;
  const time = document.getElementById("time").value;
  if(!date || !time || !sel){ msg.textContent = "Fill date, time, and pick a place."; return; }
  const p = places[+sel.value];
  const r = await fetch("/submit?t=" + TOKEN, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({date, time, lat: p.lat, lon: p.lon, tz: p.tz, place: p.label})
  });
  const j = await r.json();
  if(r.ok){ document.body.innerHTML = "<h2>Done. Go back to Ultron.</h2>"; }
  else { msg.textContent = j.error; }
}
</script>
"""


def _check_time(date: str, time: str, tz: str) -> str | None:
    """Return error text or None. Same gap/fold logic as MCP timeutil."""
    try:
        naive = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        z = ZoneInfo(tz)
    except Exception:
        return "bad date, time, or timezone."
    if naive > datetime.now():
        return "birth date is in the future."
    a = naive.replace(tzinfo=z, fold=0)
    b = naive.replace(tzinfo=z, fold=1)
    if a.utcoffset() != b.utcoffset():
        return "that local time is skipped or repeated (DST change). Pick a different time."
    return None


def collect_birth(timeout: int = 300) -> dict | None:
    """Open browser form. Block until submit or timeout. Return birth dict or None."""
    token = secrets.token_urlsafe(16)
    app = Flask(__name__)
    result: dict = {}
    done = threading.Event()

    def ok_token() -> bool:
        return request.args.get("t") == token

    @app.get("/")
    def index():
        if not ok_token():
            return "forbidden", 403
        return render_template_string(PAGE, token=token)

    @app.get("/search")
    def search():
        if not ok_token():
            return "forbidden", 403
        q = request.args.get("q", "").strip()
        try:
            r = httpx.get(GEO_URL, params={"name": q, "count": 5,
                                           "language": "en", "format": "json"},
                          timeout=10)
            r.raise_for_status()
        except httpx.HTTPError:
            return jsonify([])
        out = []
        for x in r.json().get("results", []):
            if not x.get("timezone"):
                continue
            label = ", ".join(p for p in (x.get("name"), x.get("admin1"),
                                          x.get("country")) if p)
            out.append({"label": label, "lat": x["latitude"],
                        "lon": x["longitude"], "tz": x["timezone"]})
        return jsonify(out)

    @app.post("/submit")
    def submit():
        if not ok_token():
            return jsonify(error="forbidden"), 403
        d = request.get_json(silent=True) or {}
        try:
            birth = {"date": str(d["date"]), "time": str(d["time"]),
                     "lat": float(d["lat"]), "lon": float(d["lon"]),
                     "tz": str(d["tz"])}
        except (KeyError, ValueError):
            return jsonify(error="missing or bad fields."), 400
        if not (-90 <= birth["lat"] <= 90 and -180 <= birth["lon"] <= 180):
            return jsonify(error="lat/lon out of range."), 400
        err = _check_time(birth["date"], birth["time"], birth["tz"])
        if err:
            return jsonify(error=err), 400
        birth["place"] = str(d.get("place", ""))
        result.update(birth)
        done.set()
        return jsonify(ok=True)

    srv = make_server("127.0.0.1", 0, app)
    port = srv.server_port
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    webbrowser.open(f"http://127.0.0.1:{port}/?t={token}")

    got = done.wait(timeout)
    threading.Timer(1.0, srv.shutdown).start()   # let the "Done" response flush
    return dict(result) if got else None