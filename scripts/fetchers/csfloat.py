"""CSFloat fetcher — stable public REST API baseline.

Endpoint: https://csfloat.com/api/v1/listings
Returns active marketplace listings. We query lowest-price listings that match
each tracked item's market_hash_name and take the cheapest. Prices come back in
US cents -> divide by 100 for USD.

An optional CSFLOAT_API_KEY env var raises rate limits but is not required for
the public listings endpoint.
"""

from __future__ import annotations

import os
import sys

# Allow running as `python fetchers/csfloat.py` from the scripts/ dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import market_hash_name, request_with_retries, run_fetcher

API = "https://csfloat.com/api/v1/listings"

HEADERS = {
    "User-Agent": "cs2-price-checker/0.1 (+https://github.com)",
    "Accept": "application/json",
}
_key = os.environ.get("CSFLOAT_API_KEY")
if _key:
    HEADERS["Authorization"] = _key


def fetch_one(item: dict) -> dict:
    name = market_hash_name(item)
    params = {
        "market_hash_name": name,
        "sort_by": "lowest_price",
        "limit": 1,
    }
    resp = request_with_retries(API, headers=HEADERS, params=params, retries=3)
    if resp is None:
        return {"price": None, "online": False}

    try:
        data = resp.json()
    except ValueError:
        return {"price": None, "online": False}

    listings = data.get("data") if isinstance(data, dict) else data
    if not listings:
        return {"price": None, "online": False}

    first = listings[0]
    cents = first.get("price")  # US cents
    if cents is None:
        return {"price": None, "online": False}

    listing_id = first.get("id")
    url = f"https://csfloat.com/item/{listing_id}" if listing_id else None

    return {
        "price": round(cents / 100.0, 2),
        "currency": "USD",
        "online": True,
        "url": url,
        "sleep": 1.0,
    }


if __name__ == "__main__":
    run_fetcher("csfloat", fetch_one)
