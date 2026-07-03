"""Youpin898 (悠悠有品) fetcher — PRIORITY source.

No official API. Uses the internal mobile/market endpoint. These endpoints
change periodically and are anti-bot protected, so this fetcher is written
defensively: realistic headers, retries, and per-item offline isolation.

Youpin's public price-query endpoint expects a POST with a JSON body keyed on
the item's market/template name. We search by keyword and take the lowest
on-sale price. Prices are CNY.

If the endpoint shape changes (very likely over time), each item simply flags
offline instead of breaking the run — check scripts/data_raw/youpin898.json
and adjust the parse below.
"""

from __future__ import annotations

import json
import os
import sys
import time

import requests

# Allow running as `python fetchers/youpin898.py` from the scripts/ dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import TRACKED_ITEMS, market_hash_name, now_iso, write_raw

SEARCH_API = "https://api.youpin898.com/api/homepage/pc/goods/market/querySaleTemplate"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    ),
    "Referer": "https://www.youpin898.com/",
    "Origin": "https://www.youpin898.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
    "App-Version": "5.26.0",
    "AppType": "1",
}


def _query(keyword: str) -> dict | None:
    body = {"keyWords": keyword, "pageIndex": 1, "pageSize": 10}
    for attempt in range(3):
        try:
            resp = requests.post(
                SEARCH_API, headers=HEADERS, data=json.dumps(body), timeout=15
            )
            if resp.status_code == 200:
                return resp.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.5 ** attempt)  # exponential backoff
    return None


def fetch_one(item: dict) -> dict:
    keyword = market_hash_name(item)
    data = _query(keyword)
    if not data:
        return {"price": None, "online": False}

    # Response shape (subject to change): payload.list[] with .price (CNY).
    payload = data.get("Data") or data.get("data") or {}
    rows = payload.get("list") or payload.get("Rows") or []
    if not rows:
        return {"price": None, "online": False}

    def price_of(row: dict):
        for key in ("price", "Price", "salePrice", "minSellPrice"):
            if row.get(key) is not None:
                try:
                    return float(row[key])
                except (TypeError, ValueError):
                    continue
        return None

    priced = [(price_of(r), r) for r in rows]
    priced = [(p, r) for p, r in priced if p is not None]
    if not priced:
        return {"price": None, "online": False}

    price, row = min(priced, key=lambda t: t[0])
    tid = row.get("templateId") or row.get("id")
    url = f"https://www.youpin898.com/goodInfo?id={tid}" if tid else None

    return {
        "price": round(price, 2),
        "currency": "CNY",
        "online": True,
        "url": url,
    }


def main() -> None:
    print(f"[youpin898] fetching {len(TRACKED_ITEMS)} items")
    records = []
    for item in TRACKED_ITEMS:
        try:
            result = fetch_one(item)
        except Exception as exc:  # isolation
            print(f"  ! {item['item_name']}: {exc}")
            result = {"price": None, "online": False}
        records.append(
            {
                "item_name": item["item_name"],
                "category": item.get("category", "gun"),
                "wear": item.get("wear"),
                "stattrak": item.get("stattrak", False),
                "souvenir": item.get("souvenir", False),
                "phase": item.get("phase"),
                "price": result.get("price"),
                "currency": result.get("currency"),
                "online": bool(result.get("online")) and result.get("price") is not None,
                "last_updated": now_iso(),
                "url": result.get("url"),
            }
        )
        time.sleep(1.2)
    write_raw("youpin898", records)


if __name__ == "__main__":
    main()
