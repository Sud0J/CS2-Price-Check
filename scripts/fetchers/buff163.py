"""Buff163 fetcher — PRIORITY source.

No official API. We use the internal market endpoint:
    https://buff.163.com/api/market/goods

This endpoint is fragile and anti-bot protected. Strategy:
- Realistic browser headers (User-Agent, Referer, Accept-Language).
- Search by market_hash_name via the `search` param, take the best match.
- Retries + backoff via common.request_with_retries.
- On ANY failure for an item, mark it offline rather than crashing.

Prices from Buff come as CNY. The optional BUFF_COOKIE env var (a logged-in
session cookie) dramatically reduces blocking; without it the endpoint often
returns empty/blocked, which we handle gracefully by flagging the item offline.
"""

from __future__ import annotations

import os
import sys

# Allow running as `python fetchers/buff163.py` from the scripts/ dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import market_hash_name, request_with_retries, run_fetcher

API = "https://buff.163.com/api/market/goods"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://buff.163.com/market/csgo",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}

_cookie = os.environ.get("BUFF_COOKIE")
if _cookie:
    HEADERS["Cookie"] = _cookie


def fetch_one(item: dict) -> dict:
    name = market_hash_name(item)
    params = {
        "game": "csgo",
        "page_num": 1,
        "search": name,
        "sort_by": "price.asc",
    }
    resp = request_with_retries(API, headers=HEADERS, params=params, retries=3)
    if resp is None:
        return {"price": None, "online": False}

    try:
        data = resp.json()
    except ValueError:
        # Non-JSON body usually means a block / captcha page.
        return {"price": None, "online": False}

    items = (data.get("data") or {}).get("items") or []
    if not items:
        return {"price": None, "online": False}

    # Prefer an exact market_hash_name match; else take the cheapest listed.
    match = next(
        (it for it in items if it.get("market_hash_name") == name),
        items[0],
    )
    sell_min = match.get("sell_min_price")
    if sell_min is None:
        return {"price": None, "online": False}

    goods_id = match.get("id")
    url = f"https://buff.163.com/goods/{goods_id}" if goods_id else None

    return {
        "price": round(float(sell_min), 2),
        "currency": "CNY",
        "online": True,
        "url": url,
        "sleep": 1.2,  # be polite; Buff is rate-limit sensitive
    }


if __name__ == "__main__":
    run_fetcher("buff163", fetch_one)
