"""Steam trade-link inventory client — standard library only.

Given a trade link like
  https://steamcommunity.com/tradeoffer/new/?partner=811805844&token=zlcpGCGJ
we resolve the partner's SteamID64 and load the SAME inventory the Steam
trade window shows.

Why not the public inventory endpoint? Freshly traded items can be hidden
from the public inventory for ~10 days, while the trade window shows them as
soon as the 7-day trade protection ends. So we hit the trade-window endpoint
(`/tradeoffer/new/partnerinventory/`) first — it needs YOUR Steam login
cookies (you must be logged in to open a trade window):

  .secrets.env:
    STEAM_SESSIONID="..."        # cookie `sessionid` on steamcommunity.com
    STEAM_LOGIN_SECURE="..."     # cookie `steamLoginSecure`

Get them: log in at steamcommunity.com -> DevTools -> Application -> Cookies
-> https://steamcommunity.com -> copy `sessionid` and `steamLoginSecure`.

If the cookies are missing/expired we fall back to the public inventory
endpoint (no login needed, but may miss recently traded items).

Results are cached in-memory for CACHE_TTL seconds per partner.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

STEAMID64_BASE = 76561197960265728  # individual accounts: steamid64 = base + accountid
APP_ID = 730          # CS2
CONTEXT_ID = 2
CACHE_TTL = int(os.environ.get("STEAM_CACHE_TTL", "120"))
ICON_BASE = "https://community.fastly.steamstatic.com/economy/image/"

_cache: dict[str, tuple[float, object]] = {}


class SteamError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Trade link parsing
# ---------------------------------------------------------------------------
_LINK_RE = re.compile(
    r"steamcommunity\.com/tradeoffer/new/\?.*partner=(\d+)", re.IGNORECASE)


def parse_trade_link(link: str) -> tuple[int, str | None]:
    """Return (partner accountid, token) from a trade offer link.

    Also accepts a bare partner id ('811805844') or a steamid64.
    """
    link = (link or "").strip()
    if not link:
        raise SteamError("empty trade link")
    if link.isdigit():
        n = int(link)
        return (n - STEAMID64_BASE, None) if n >= STEAMID64_BASE else (n, None)
    m = _LINK_RE.search(link)
    if not m:
        raise SteamError("not a valid trade link (expected .../tradeoffer/new/?partner=...)")
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    token = (qs.get("token") or [None])[0]
    return int(m.group(1)), token


def to_steamid64(partner: int) -> int:
    return partner + STEAMID64_BASE


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _get_json(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise SteamError("Steam login expired (401) — refresh STEAM_LOGIN_SECURE")
        if exc.code == 403:
            raise SteamError("Steam refused (403) — inventory private or bad token/cookies")
        if exc.code == 429:
            raise SteamError("Steam rate-limited (429) — wait a minute and retry")
        raise SteamError(f"Steam HTTP {exc.code}")
    except urllib.error.URLError as exc:
        raise SteamError(f"network error reaching Steam: {exc.reason}")


def _steam_cookies() -> tuple[str, str] | None:
    sid = os.environ.get("STEAM_SESSIONID", "").strip()
    sls = os.environ.get("STEAM_LOGIN_SECURE", "").strip()
    return (sid, sls) if sid and sls else None


# ---------------------------------------------------------------------------
# Inventory normalisation
# ---------------------------------------------------------------------------
def _norm_desc(d: dict) -> dict:
    return {
        "market_hash_name": d.get("market_hash_name") or d.get("market_name") or d.get("name"),
        "name": d.get("name"),
        "type": d.get("type"),
        "icon_url": (ICON_BASE + d["icon_url"] + "/144fx144f") if d.get("icon_url") else None,
        "tradable": bool(int(d.get("tradable") or 0)),
        "marketable": bool(int(d.get("marketable") or 0)),
        "name_color": d.get("name_color"),
    }


def _group(assets_with_desc: list[tuple[str, dict]]) -> list[dict]:
    """Group per-asset entries by market_hash_name -> item with count."""
    out: dict[str, dict] = {}
    for asset_id, desc in assets_with_desc:
        key = desc.get("market_hash_name")
        if not key:
            continue
        it = out.get(key)
        if it is None:
            it = {**desc, "count": 0, "asset_ids": []}
            out[key] = it
        it["count"] += 1
        it["asset_ids"].append(asset_id)
        # if any copy is tradable, surface the item as tradable
        it["tradable"] = it["tradable"] or desc["tradable"]
    return sorted(out.values(), key=lambda i: i["market_hash_name"].lower())


def _fetch_trade_window(steamid64: int, partner: int, token: str | None,
                        cookies: tuple[str, str]) -> list[dict]:
    """Inventory as the Steam TRADE WINDOW sees it (needs login cookies)."""
    sid, sls = cookies
    referer = f"https://steamcommunity.com/tradeoffer/new/?partner={partner}"
    if token:
        referer += f"&token={token}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": f"sessionid={sid}; steamLoginSecure={sls}",
    }
    entries: list[tuple[str, dict]] = []
    start = 0
    for _page in range(20):  # safety bound
        params = {"sessionid": sid, "partner": steamid64,
                  "appid": APP_ID, "contextid": CONTEXT_ID, "l": "english"}
        if start:
            params["start"] = start
        url = ("https://steamcommunity.com/tradeoffer/new/partnerinventory/?"
               + urllib.parse.urlencode(params))
        data = _get_json(url, headers)
        if not data or not data.get("success"):
            err = (data or {}).get("strError") or "trade window inventory unavailable"
            raise SteamError(str(err))
        descs = {k: _norm_desc(v) for k, v in (data.get("rgDescriptions") or {}).items()}
        for asset_id, a in (data.get("rgInventory") or {}).items():
            d = descs.get(f"{a.get('classid')}_{a.get('instanceid')}")
            if d:
                entries.append((asset_id, d))
        if not data.get("more"):
            break
        start = data.get("more_start") or 0
        time.sleep(0.4)
    return _group(entries)


def _fetch_public(steamid64: int) -> list[dict]:
    """Public inventory endpoint (no login). May hide recently traded items."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    entries: list[tuple[str, dict]] = []
    last_assetid = None
    for _page in range(20):
        params = {"l": "english", "count": 2000}
        if last_assetid:
            params["start_assetid"] = last_assetid
        url = (f"https://steamcommunity.com/inventory/{steamid64}/{APP_ID}/{CONTEXT_ID}?"
               + urllib.parse.urlencode(params))
        data = _get_json(url, headers)
        if not data or not data.get("success"):
            raise SteamError("public inventory unavailable (private profile?)")
        descs = {f"{d.get('classid')}_{d.get('instanceid')}": _norm_desc(d)
                 for d in (data.get("descriptions") or [])}
        for a in (data.get("assets") or []):
            d = descs.get(f"{a.get('classid')}_{a.get('instanceid')}")
            if d:
                entries.append((a.get("assetid"), d))
        if not data.get("more_items"):
            break
        last_assetid = data.get("last_assetid")
        time.sleep(0.4)
    return _group(entries)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def trade_inventory(link: str) -> dict:
    """Items visible for the partner in `link`.

    Returns {partner, steamid64, source, items:[{market_hash_name, icon_url,
    count, tradable, marketable, ...}], warning?}.
    source: 'trade_window' (login cookies) or 'public' (fallback).
    """
    partner, token = parse_trade_link(link)
    steamid64 = to_steamid64(partner)

    ck = f"inv:{steamid64}"
    hit = _cache.get(ck)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]

    result: dict = {"partner": partner, "steamid64": str(steamid64)}
    cookies = _steam_cookies()
    items = None
    if cookies:
        try:
            items = _fetch_trade_window(steamid64, partner, token, cookies)
            result["source"] = "trade_window"
        except SteamError as exc:
            result["warning"] = f"trade window failed ({exc}); showing public inventory"
    if items is None:
        items = _fetch_public(steamid64)
        result.setdefault("source", "public")
        if not cookies:
            result["warning"] = ("no Steam cookies set — using PUBLIC inventory, which can "
                                 "hide items traded in the last ~10 days. Add STEAM_SESSIONID "
                                 "+ STEAM_LOGIN_SECURE to scripts/.secrets.env for the "
                                 "trade-window view.")
    result["items"] = items
    result["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _cache[ck] = (time.time(), result)
    return result
