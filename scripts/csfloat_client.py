"""CSFloat on-demand client — standard library only.

Requires CSFLOAT_API_KEY in env (free: csfloat.com -> profile -> Developer tab).
CSFloat prices are USD and name-based, so they cannot distinguish Doppler phase.

price_by_name(market_hash_name) -> {price_usd, online, url, updated}
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

API = "https://csfloat.com/api/v1/listings"
CACHE_TTL = int(os.environ.get("CACHE_TTL", "60"))
_cache: dict = {}


def price_by_name(name: str) -> dict:
    key = os.environ.get("CSFLOAT_API_KEY")
    if not key:
        return {"price_usd": None, "online": False, "error": "no api key"}

    ck = f"cf:{name.lower().strip()}"
    hit = _cache.get(ck)
    if hit and (time.time() - hit[0]) < CACHE_TTL:
        return hit[1]

    lowest = None
    url = None
    err = None
    try:
        full = API + "?" + urllib.parse.urlencode(
            {"market_hash_name": name, "sort_by": "lowest_price", "type": "buy_now", "limit": 1})
        req = urllib.request.Request(full, headers={
            "Authorization": key, "Accept": "application/json",
            "User-Agent": "cs2-price-checker/0.1"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        listings = data.get("data") if isinstance(data, dict) else data
        # keep only fixed-price (buy_now) listings; never a bid/auction price
        buy_now = [l for l in (listings or []) if l.get("type") in (None, "buy_now")]
        if buy_now:
            cents = buy_now[0].get("price")
            lowest = round(cents / 100.0, 2) if cents is not None else None
            lid = buy_now[0].get("id")
            url = f"https://csfloat.com/item/{lid}" if lid else None
        else:
            err = "no buy-now listings for this exact name"
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:120]
        except Exception:
            pass
        err = f"HTTP {exc.code} {detail}".strip()
        if exc.code in (401, 403):
            err = f"API key rejected (HTTP {exc.code})"
        elif exc.code == 429:
            err = "rate-limited (429)"
    except (urllib.error.URLError, ValueError, KeyError, TypeError) as exc:
        err = f"{type(exc).__name__}: {exc}"

    result = {
        "price_usd": lowest,
        "online": lowest is not None,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "url": url or "https://csfloat.com",
    }
    if err:
        result["error"] = err
    if lowest is not None:  # never cache failures — retry next click
        _cache[ck] = (time.time(), result)
    return result
