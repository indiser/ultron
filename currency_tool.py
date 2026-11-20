from datetime import date as _date
import math
import re
import time
import httpx

__all__ = ["convert_currency", "check_frankfurter_uptime"]

_ENDPOINTS = (
    ("v1", "https://api.frankfurter.dev/v1"),
    ("legacy", "https://api.frankfurter.app"),
)

_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
_HEADERS = {"User-Agent": "UltronAgent/1.0"}

_ALIASES: dict[str, str] = {
    "$": "USD",
    "US$": "USD",
    "DOLLAR": "USD",
    "DOLLARS": "USD",
    "US DOLLAR": "USD",
    "₹": "INR",
    "RS": "INR",
    "RS.": "INR",
    "INR": "INR",
    "RUPEE": "INR",
    "RUPEES": "INR",
    "INDIAN RUPEE": "INR",
    "€": "EUR",
    "EURO": "EUR",
    "EUROS": "EUR",
    "£": "GBP",
    "POUND": "GBP",
    "POUNDS": "GBP",
    "STERLING": "GBP",
    "¥": "JPY",
    "YEN": "JPY",
    "YUAN": "CNY",
    "RMB": "CNY",
    "A$": "AUD",
    "AU$": "AUD",
    "C$": "CAD",
    "CA$": "CAD",
    "S$": "SGD",
    "SG$": "SGD",
    "FRANC": "CHF",
    "WON": "KRW",
}


def _norm_currency(raw: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("currency code is empty")
    cleaned = re.sub(r"\s+", " ", raw.strip().upper())
    code = _ALIASES.get(cleaned, cleaned)
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError(f"invalid currency '{raw}'. Use 3-letter ISO code like USD, INR, EUR, GBP, JPY.")
    return code


def _parse_amount(raw: float | int | str) -> float:
    if isinstance(raw, bool):
        raise ValueError("amount must be a number")
    if isinstance(raw, str):
        cleaned = raw.strip().replace(",", "")
        if not cleaned:
            raise ValueError("amount is empty")
        val = float(cleaned)
    else:
        val = float(raw)
    if math.isnan(val) or math.isinf(val):
        raise ValueError("amount must be finite")
    if val < 0:
        raise ValueError("amount cannot be negative")
    return val


def _validate_date(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "latest"
    try:
        parsed = _date.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"invalid date '{s}'. Use YYYY-MM-DD format.") from exc
    if parsed > _date.today():
        raise ValueError(f"date '{s}' is in the future. Leave date empty for latest rate.")
    return parsed.isoformat()


async def check_frankfurter_uptime() -> tuple[bool, str]:
    """Probe primary and mirror Frankfurter endpoints."""
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        for kind, base in _ENDPOINTS:
            params = {"base": "USD", "symbols": "EUR"} if kind == "v1" else {"from": "USD", "to": "EUR"}
            t0 = time.monotonic()
            try:
                resp = await client.get(f"{base}/latest", params=params)
                ms = round((time.monotonic() - t0) * 1000)
                if resp.status_code == 200 and "rates" in resp.json():
                    return True, f"Frankfurter reachable via {base} ({ms} ms)"
                errors.append(f"{base} -> HTTP {resp.status_code}")
            except Exception as exc:
                errors.append(f"{base} -> {type(exc).__name__}: {exc}")
    return False, "; ".join(errors)


async def convert_currency(
    amount: float | int | str,
    from_currency: str,
    to_currency: str,
    date: str = "",
) -> str:
    try:
        amt = _parse_amount(amount)
        src = _norm_currency(from_currency)
        dst = _norm_currency(to_currency)
        path_date = _validate_date(date)
    except ValueError as exc:
        return f"error: {exc}"

    if src == dst:
        return f"{amt:,.2f} {src} = {amt:,.2f} {dst} (rate: 1, same currency)"

    last_err = "unknown network error"
    data: dict | None = None

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        for kind, base in _ENDPOINTS:
            params = (
                {"base": src, "symbols": dst}
                if kind == "v1"
                else {"from": src, "to": dst}
            )
            try:
                resp = await client.get(f"{base}/{path_date}", params=params)
                if resp.status_code == 404:
                    return (
                        f"error: currency pair {src}->{dst} not supported by Frankfurter (ECB feed). "
                        f"Use web_search for {src} to {dst} exchange rate."
                    )
                if resp.status_code >= 500:
                    last_err = f"{base} HTTP {resp.status_code}"
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.HTTPStatusError as exc:
                return f"error: currency API rejected request (HTTP {exc.response.status_code})."
            except Exception as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                continue

    if not data or "rates" not in data or dst not in data["rates"]:
        return f"error: currency lookup failed ({last_err}). Try web_search if API is down."

    rate = float(data["rates"][dst])
    converted = amt * rate
    rate_date = data.get("date", path_date)
    inv_rate = (1.0 / rate) if rate > 0 else 0.0

    return (
        f"{amt:,.2f} {src} = {converted:,.2f} {dst} "
        f"(rate: 1 {src} = {rate:.6g} {dst}, 1 {dst} = {inv_rate:.6g} {src}, ECB date: {rate_date})"
    )