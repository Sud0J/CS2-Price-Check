"""Buff163 on-demand client — standard library only (no `requests`).

search(keyword)      -> finishes (relevance-filtered) with their variants
price(goods_id)      -> fresh lowest price for one variant
price_by_name(name)  -> lowest price for an exact market_hash_name
All cached in-memory for CACHE_TTL seconds. Requires BUFF_COOKIE in env.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error

API_GOODS = "https://buff.163.com/api/market/goods"
API_SELL = "https://buff.163.com/api/market/goods/sell_order"
CACHE_TTL = int(os.environ.get("CACHE_TTL", "60"))
WEARS = ["Factory New", "Minimal Wear", "Field-Tested", "Well-Worn", "Battle-Scarred"]

# Short terms Buff's search handles poorly -> expand so it returns real matches.
ALIASES = {
    "ak": "AK-47", "ak47": "AK-47", "ak-47": "AK-47",
    "m4": "M4A4", "m4a4": "M4A4", "m4a1": "M4A1-S", "m4a1s": "M4A1-S", "m4s": "M4A1-S",
    "awp": "AWP", "usp": "USP-S", "usps": "USP-S",
    "glock": "Glock-18", "deagle": "Desert Eagle", "desert eagle": "Desert Eagle",
    "kara": "Karambit", "karambit": "Karambit", "m9": "M9 Bayonet",
    "ssg": "SSG 08", "ssg08": "SSG 08", "aug": "AUG", "sg": "SG 553",
    "mac10": "MAC-10", "mp9": "MP9", "p90": "P90", "famas": "FAMAS",
    "tec9": "Tec-9", "tec-9": "Tec-9", "cz": "CZ75-Auto", "p250": "P250",
    "galil": "Galil AR", "nova": "Nova", "mag7": "MAG-7", "negev": "Negev",
}

_cache: dict[str, tuple[float, object]] = {}

# Buff's own CNY->USD rate, derived from Buff's data so USD matches Buff's site.
_buff_rate = 6.8  # sensible default until a real response updates it


def _update_rate(item: dict) -> None:
    """Derive Buff's CNY/USD rate from an item's Steam price pair."""
    global _buff_rate
    gi = item.get("goods_info") or {}
    try:
        usd = float(gi.get("steam_price"))
        cny = float(gi.get("steam_price_cny"))
    except (TypeError, ValueError):
        return
    if usd > 0:
        r = cny / usd
        if 5.0 <= r <= 8.5:  # guard against bad data
            _buff_rate = r


def buff_usd(cny) -> float | None:
    try:
        return round(float(cny) / _buff_rate, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def get_buff_rate() -> float:
    return _buff_rate


def _headers() -> dict:
    h = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://buff.163.com/market/csgo",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
    }
    if os.environ.get("BUFF_COOKIE"):
        h["Cookie"] = os.environ["BUFF_COOKIE"]
    return h


def _get_json(url: str, params: dict, timeout: int = 20, attempts: int = 2) -> dict:
    """GET with retry on timeout/network error, then Buff-code check."""
    full = url + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(full, headers=_headers())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(1.0)
                continue
            raise RuntimeError(f"Buff network error: {last}") from exc
    # Buff wraps everything in {"code": "OK", ...}; anything else is an error
    # (e.g. "Login Required", "Action Forbidden") and must not be treated as
    # an empty result.
    code = (data or {}).get("code")
    if code not in (None, "OK"):
        msg = (data or {}).get("error") or (data or {}).get("msg") or ""
        raise RuntimeError(f"Buff refused: {code} {msg}".strip())
    return data


def selftest() -> dict:
    """Quick Buff connectivity/login check for /api/buff_selftest."""
    out = {"cookie_set": bool(os.environ.get("BUFF_COOKIE"))}
    t0 = time.time()
    try:
        data = _get_json(API_GOODS, {"game": "csgo", "page_num": 1,
                                     "search": "AK-47 | Redline",
                                     "_": int(time.time() * 1000)})
        items = ((data or {}).get("data") or {}).get("items") or []
        out["ok"] = True
        out["items_returned"] = len(items)
        if items:
            out["sample"] = items[0].get("market_hash_name")
            out["sample_price_cny"] = items[0].get("sell_min_price")
    except Exception as exc:  # show the reason, whatever it is
        out["ok"] = False
        out["error"] = str(exc)
    out["elapsed_s"] = round(time.time() - t0, 1)
    return out


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key: str, value):
    _cache[key] = (time.time(), value)


_WEAR_RE = re.compile(r"\(([^)]+)\)\s*$")


def _search_keyword(market_hash_name: str) -> str:
    """Reduce a market_hash_name to something Buff's search actually handles:
    strip the star, StatTrak/Souvenir prefixes, the trailing (wear) and the
    pipe. '★ Butterfly Knife | Fade (Field-Tested)' -> 'Butterfly Knife Fade'."""
    s = market_hash_name.replace("★", " ")
    s = re.sub(r"^\s*StatTrak(™)?\s*", "", s)
    s = re.sub(r"^\s*Souvenir\s*", "", s)
    s = re.sub(r"\s*\([^)]+\)\s*$", "", s)
    s = s.replace("|", " ")
    return re.sub(r"\s+", " ", s).strip()


def _norm_name(s: str) -> str:
    """Normalize a full market_hash_name for tolerant comparison."""
    s = (s or "").replace("★", " ").replace("™", " ").replace("|", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def _pos_price(p) -> float | None:
    """Buff uses '0' / 0 / '' for 'no listings' — only a positive number is a
    real price."""
    try:
        v = round(float(p), 2)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def parse_name(name: str) -> dict:
    original = name
    star = name.startswith("★")
    if star:
        name = name.lstrip("★").strip()
    souvenir = name.startswith("Souvenir ")
    if souvenir:
        name = name[len("Souvenir "):]
    stattrak = name.startswith("StatTrak")
    if stattrak:
        name = re.sub(r"^StatTrak(™)?\s*", "", name)
    wear = None
    m = _WEAR_RE.search(name)
    if m and m.group(1) in WEARS:
        wear = m.group(1)
        name = name[: m.start()].strip()
    base = name.strip()
    return {
        "market_hash_name": original,
        "base": ("★ " + base) if star else base,
        "category": "knife" if star else "gun",
        "wear": wear,
        "stattrak": stattrak,
        "souvenir": souvenir,
    }


def _variant_label(v: dict) -> str:
    bits = []
    if v["stattrak"]:
        bits.append("StatTrak™")
    if v["souvenir"]:
        bits.append("Souvenir")
    if not bits:
        bits.append("Normal")
    if v["wear"]:
        bits.append(v["wear"])
    return " · ".join(bits)


def _norm(s: str) -> str:
    # lower, drop star/pipe/dashes so "AK-47 | Redline" -> "ak 47 redline"
    s = (s or "").lower().replace("★", " ").replace("|", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def _relevant(base: str, query: str) -> bool:
    """True if every token of the query appears in the finish name."""
    b = _norm(base)
    tokens = [t for t in _norm(query).split() if t]
    return all(t in b for t in tokens)


def _rank(base: str, query: str) -> tuple:
    b = _norm(base)
    q = _norm(query)
    return (0 if b.startswith(q) else 1, len(b))


def search(keyword: str) -> list[dict]:
    original = keyword.strip()
    key = f"search:{original.lower()}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # Expand short aliases so Buff actually returns relevant items.
    buff_query = ALIASES.get(original.lower(), original)

    params = {"game": "csgo", "page_num": 1, "page_size": 80,
              "search": buff_query, "_": int(time.time() * 1000)}
    data = _get_json(API_GOODS, params, timeout=12)
    items = ((data or {}).get("data") or {}).get("items") or []

    groups: dict[str, dict] = {}
    for it in items:
        mhn = it.get("market_hash_name") or it.get("name") or ""
        if not mhn:
            continue
        parsed = parse_name(mhn)
        _update_rate(it)
        g = groups.setdefault(parsed["base"], {
            "base": parsed["base"],
            "category": parsed["category"],
            "image": (it.get("goods_info") or {}).get("icon_url"),
            "stattrak_possible": False,
            "souvenir_possible": False,
            "variants": [],
        })
        if parsed["stattrak"]:
            g["stattrak_possible"] = True
        if parsed["souvenir"]:
            g["souvenir_possible"] = True
        price = _pos_price(it.get("sell_min_price"))
        g["variants"].append({
            "goods_id": it.get("id"),
            "wear": parsed["wear"],
            "stattrak": parsed["stattrak"],
            "souvenir": parsed["souvenir"],
            "label": _variant_label(parsed),
            "price_cny": price,
            "market_hash_name": mhn,
        })

    # Relevance filter: only finishes that actually match what the user typed.
    # Match against the original query AND the expanded alias (so "ak" keeps
    # "AK-47" even though the raw token is "ak").
    match_query = buff_query if buff_query != original else original
    result = [g for g in groups.values()
              if _relevant(g["base"], original) or _relevant(g["base"], match_query)]
    result.sort(key=lambda g: _rank(g["base"], match_query))

    _cache_put(key, result)
    return result


def price(goods_id: int) -> dict:
    key = f"price:{goods_id}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    err = None
    lowest = None
    try:
        params = {"game": "csgo", "goods_id": goods_id, "page_num": 1,
                  "sort_by": "price.asc", "_": int(time.time() * 1000)}
        data = _get_json(API_SELL, params)
        orders = ((data or {}).get("data") or {}).get("items") or []
        lowest = _pos_price(orders[0]["price"]) if orders else None
        if lowest is None:
            err = "no live sell orders"
    except Exception as exc:
        err = str(exc)
    result = {
        "price_cny": lowest,
        "price_usd": buff_usd(lowest) if lowest is not None else None,
        "online": lowest is not None,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "url": f"https://buff.163.com/goods/{goods_id}",
    }
    if err:
        result["error"] = err
    if lowest is not None:  # never cache failures — retry next click
        _cache_put(key, result)
    return result


def price_by_name(name: str) -> dict:
    key = f"pn:{name.lower().strip()}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    lowest = None
    goods_id = None
    err = None
    try:
        # Search with a simplified keyword (Buff's search fails on ★/(wear)),
        # then pick the row whose market_hash_name matches exactly. Walk up to
        # 3 pages — popular finishes ("Fade") return many rows and the wear we
        # want may not be on page 1.
        tgt = _norm_name(name)
        match = None
        seen = 0
        for pg in range(1, 4):
            params = {"game": "csgo", "page_num": pg, "page_size": 80,
                      "search": _search_keyword(name), "_": int(time.time() * 1000)}
            data = _get_json(API_GOODS, params)
            d = (data or {}).get("data") or {}
            items = d.get("items") or []
            seen += len(items)
            match = next((it for it in items
                          if (it.get("market_hash_name") or "") == name), None)
            if match is None:  # tolerant fallback: ★/™/| spacing differences
                match = next((it for it in items
                              if _norm_name(it.get("market_hash_name") or "") == tgt), None)
            try:
                total_pages = int(d.get("total_page") or 1)
            except (TypeError, ValueError):
                total_pages = 1
            if match is not None or not items or pg >= total_pages:
                break
        if match:
            _update_rate(match)
            goods_id = match.get("id")
            lowest = _pos_price(match.get("sell_min_price"))
            if lowest is None:
                err = "listed on Buff but no live sell orders"
        else:
            err = f"no matching item among {seen} Buff results"
    except Exception as exc:
        err = str(exc)
    result = {
        "price_cny": lowest,
        "price_usd": buff_usd(lowest) if lowest is not None else None,
        "online": lowest is not None,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "url": f"https://buff.163.com/goods/{goods_id}" if goods_id else "https://buff.163.com/market/csgo",
        "goods_id": goods_id,
    }
    if err:
        result["error"] = err
    if lowest is not None:  # never cache failures — retry next click
        _cache_put(key, result)
    return result


# CS:GO Doppler / Gamma Doppler paint indices -> phase name. These are stable.
PAINT_PHASES = {
    # regular Doppler
    415: "Ruby", 416: "Sapphire", 417: "Black Pearl",
    418: "Phase 1", 419: "Phase 2", 420: "Phase 3", 421: "Phase 4",
    # Gamma Doppler
    568: "Emerald", 569: "Phase 1", 570: "Phase 2", 571: "Phase 3", 572: "Phase 4",
}
PHASE_ORDER = ["Phase 1", "Phase 2", "Phase 3", "Phase 4",
               "Ruby", "Sapphire", "Black Pearl", "Emerald"]


def _paintindex(order: dict):
    info = (order.get("asset_info") or {}).get("info") or {}
    return info.get("paintindex", info.get("paint_index"))


def phases(goods_id: int, max_pages: int = 8) -> dict:
    """Break a Doppler/Gamma Doppler goods into per-phase lowest prices by
    reading each live listing's paintindex. Returns {phase: {price_cny}}.
    Scans the cheapest `max_pages` pages of listings, so very expensive gems
    (Ruby/Sapphire) may not always appear if none are near the price floor."""
    key = f"phases:{goods_id}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    found: dict[str, dict] = {}
    for pg in range(1, max_pages + 1):
        try:
            data = _get_json(API_SELL, {"game": "csgo", "goods_id": goods_id,
                                        "page_num": pg, "page_size": 80,
                                        "sort_by": "price.asc",
                                        "_": int(time.time() * 1000)})
        except (urllib.error.URLError, ValueError):
            break
        items = ((data or {}).get("data") or {}).get("items") or []
        if not items:
            break
        for o in items:
            ph = PAINT_PHASES.get(_paintindex(o))
            if not ph:
                continue
            try:
                price = round(float(o.get("price")), 2)
            except (TypeError, ValueError):
                continue
            if ph not in found or price < found[ph]["price_cny"]:
                found[ph] = {"price_cny": price, "price_usd": buff_usd(price)}
        if all(p in found for p in ("Phase 1", "Phase 2", "Phase 3", "Phase 4")):
            break

    ordered = {ph: found[ph] for ph in PHASE_ORDER if ph in found}
    _cache_put(key, ordered)
    return ordered
