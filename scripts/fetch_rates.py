"""Fetch currency rates once per run -> public/data/rates.json.

Two free, key-less sources:
- Frankfurter.app for USD/EUR/CNY/VND fiat cross rates (base = USD).
- Binance P2P public search for a real USDT<->VND rate, which reflects actual
  trading conditions better than a generic USD peg.

Output schema (all rates expressed as "how many X per 1 USD", plus a direct
USDT/VND for accuracy):

{
  "generated_at": "...",
  "base": "USD",
  "rates": { "USD": 1, "EUR": 0.9, "CNY": 7.1, "VND": 25400, "USDT": 1.0 },
  "usdt_vnd": 25600
}

The frontend converts any source price to the user's display currency using
these rates. If a source fails, we keep the last good value where possible and
fall back to sane defaults so the site never breaks.
"""

from __future__ import annotations

import json
import statistics

import requests

from common import PUBLIC_DATA_DIR, now_iso

FRANKFURTER = "https://api.frankfurter.app/latest"
BINANCE_P2P = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

# Sensible fallbacks if a provider is down (approximate; only used on failure).
DEFAULT_RATES = {"USD": 1.0, "EUR": 0.92, "CNY": 7.15, "VND": 25400.0, "USDT": 1.0}
DEFAULT_USDT_VND = 25600.0


def fetch_fiat() -> dict:
    """USD-based rates for EUR, CNY, VND via Frankfurter."""
    try:
        resp = requests.get(
            FRANKFURTER,
            params={"from": "USD", "to": "EUR,CNY,VND"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("rates", {})
        rates = {"USD": 1.0, "USDT": 1.0}
        for code in ("EUR", "CNY", "VND"):
            if code in data:
                rates[code] = float(data[code])
        # fill any gaps from defaults
        for code, val in DEFAULT_RATES.items():
            rates.setdefault(code, val)
        return rates
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"  ! frankfurter failed ({exc}); using defaults")
        return dict(DEFAULT_RATES)


def fetch_usdt_vnd() -> float:
    """Median of the top BUY adverts on Binance P2P for USDT priced in VND."""
    body = {
        "asset": "USDT",
        "fiat": "VND",
        "tradeType": "BUY",
        "page": 1,
        "rows": 10,
        "payTypes": [],
    }
    try:
        resp = requests.post(BINANCE_P2P, json=body, timeout=15)
        resp.raise_for_status()
        adverts = resp.json().get("data", [])
        prices = []
        for adv in adverts:
            p = adv.get("adv", {}).get("price")
            if p is not None:
                prices.append(float(p))
        if prices:
            return round(statistics.median(prices), 2)
        raise ValueError("no adverts returned")
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"  ! binance p2p failed ({exc}); using default")
        return DEFAULT_USDT_VND


def main() -> None:
    rates = fetch_fiat()
    usdt_vnd = fetch_usdt_vnd()
    # Reconcile: express USDT in the same USD-based table. 1 USDT ~ 1 USD, but
    # the VND display value should use the real P2P rate, so we store it too.
    out = {
        "generated_at": now_iso(),
        "base": "USD",
        "rates": rates,
        "usdt_vnd": usdt_vnd,
    }
    dest = PUBLIC_DATA_DIR / "rates.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rates -> {dest}: {rates}, usdt_vnd={usdt_vnd}")


if __name__ == "__main__":
    main()
