"""C5Game fetcher — EXPERIMENTAL scrape.

No stable API. We scrape the public listing search pages with BeautifulSoup.
This is the most likely source to break, so:
- It is flagged "experimental" in the merged data and the UI greys it out.
- Any parse failure flags the item offline; it never crashes the pipeline.

C5Game renders much of its market via JS, so pure HTML scraping is best-effort.
When it returns nothing, the item is simply marked offline (online: false),
which the frontend already knows how to display honestly.
"""

from __future__ import annotations

import os
import re
import sys

from bs4 import BeautifulSoup

# Allow running as `python fetchers/c5game.py` from the scripts/ dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import market_hash_name, request_with_retries, run_fetcher

SEARCH_URL = "https://www.c5game.com/csgo"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.c5game.com/",
}

_PRICE_RE = re.compile(r"[¥￥]\s*([0-9]+(?:\.[0-9]+)?)")


def fetch_one(item: dict) -> dict:
    name = market_hash_name(item)
    resp = request_with_retries(
        SEARCH_URL, headers=HEADERS, params={"keyword": name}, retries=2
    )
    if resp is None:
        return {"price": None, "online": False}

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Best-effort: pull the first CNY price token off the rendered page.
    m = _PRICE_RE.search(text)
    if not m:
        return {"price": None, "online": False}

    try:
        price = float(m.group(1))
    except ValueError:
        return {"price": None, "online": False}

    return {
        "price": round(price, 2),
        "currency": "CNY",
        "online": True,
        "url": f"https://www.c5game.com/csgo?keyword={name}",
        "sleep": 1.5,
    }


if __name__ == "__main__":
    run_fetcher("c5game", fetch_one)
