"""Currency rates — standard library only. Cached ~10 min.

- Fiat cross rates (EUR/CNY/VND per 1 USD) via Frankfurter.
- USDT<->VND from Binance P2P *SELL* adverts (price to SELL USDT for VND),
  per the requirement that USDT is based on the Binance P2P sell price.

Falls back to sane defaults if a provider is unreachable so /api/rates never
breaks the UI.
"""

from __future__ import annotations

import json
import statistics
import time
import urllib.parse
import urllib.request
import urllib.error

FRANKFURTER = "https://api.frankfurter.app/latest"
BINANCE_P2P = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
TTL = 600  # 10 minutes

DEFAULTS = {"USD": 1.0, "USDT": 1.0, "EUR": 0.92, "CNY": 7.15, "VND": 25400.0}
DEFAULT_USDT_VND = 25600.0
_cache: dict = {}


def _fiat() -> dict:
    try:
        url = FRANKFURTER + "?" + urllib.parse.urlencode({"from": "USD", "to": "EUR,CNY,VND"})
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8")).get("rates", {})
        rates = {"USD": 1.0, "USDT": 1.0}
        for c in ("EUR", "CNY", "VND"):
            if c in data:
                rates[c] = float(data[c])
        for c, v in DEFAULTS.items():
            rates.setdefault(c, v)
        return rates
    except (urllib.error.URLError, ValueError, KeyError):
        return dict(DEFAULTS)


def _usdt_vnd_sell() -> float:
    """Median price of top Binance P2P SELL adverts (USDT priced in VND)."""
    body = {"asset": "USDT", "fiat": "VND", "tradeType": "SELL",
            "page": 1, "rows": 10, "payTypes": []}
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            BINANCE_P2P, data=data,
            headers={"Content-Type": "application/json",
                     "User-Agent": "Mozilla/5.0", "Accept": "*/*"},
            method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            adverts = json.loads(r.read().decode("utf-8")).get("data", [])
        prices = [float(a["adv"]["price"]) for a in adverts if a.get("adv", {}).get("price")]
        return round(statistics.median(prices), 2) if prices else DEFAULT_USDT_VND
    except (urllib.error.URLError, ValueError, KeyError, TypeError, statistics.StatisticsError):
        return DEFAULT_USDT_VND


def get_rates() -> dict:
    now = time.time()
    if _cache and (now - _cache.get("_t", 0)) < TTL:
        return _cache["data"]
    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base": "USD",
        "rates": _fiat(),
        "usdt_vnd": _usdt_vnd_sell(),
        "usdt_vnd_source": "binance_p2p_sell",
    }
    _cache["data"] = result
    _cache["_t"] = now
    return result
