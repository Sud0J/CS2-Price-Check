"""Youpin898 (悠悠有品) on-demand client — standard library only.

Wired from a real captured request. Endpoint:
    POST https://api.youpin898.com/api/homepage/pc/goods/market/querySaleTemplate

The response returns templates each carrying `commodityHashName` (the English
market_hash_name, e.g. "★ M9 Bayonet | Fade (Factory New)") and `price` (CNY).
So we search by keyword, then match the exact commodityHashName.

Auth comes from scripts/.secrets.env (loaded by the server):
    YOUPIN_AUTHORIZATION  (JWT — expires ~10 days; re-capture when it does)
    YOUPIN_DEVICEID, YOUPIN_DEVICEUK, YOUPIN_UK

price_for(market_hash_name) -> {price_cny, online, url, updated}
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
import threading
import uuid

API = "https://api.youpin898.com/api/homepage/pc/goods/market/querySaleTemplate"
CACHE_TTL = int(os.environ.get("YOUPIN_CACHE_TTL", "300"))  # cache prices 5 min
_cache: dict = {}

# --- request pacing to avoid Youpin's 429 "too frequent" throttle ---
_lock = threading.Lock()
_last_req = [0.0]
MIN_INTERVAL = float(os.environ.get("YOUPIN_MIN_INTERVAL", "2.5"))  # seconds between calls


def _throttle():
    with _lock:
        wait = MIN_INTERVAL - (time.time() - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()


def _headers() -> dict:
    h = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.youpin898.com",
        "Referer": "https://www.youpin898.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        ),
        "platform": "pc",
        "app-version": "5.26.0",
        "appversion": "5.26.0",
        "apptype": "1",
        "secret-v": "h5_v1",
    }
    if os.environ.get("YOUPIN_AUTHORIZATION"):
        h["authorization"] = os.environ["YOUPIN_AUTHORIZATION"]
    if os.environ.get("YOUPIN_DEVICEID"):
        h["deviceid"] = os.environ["YOUPIN_DEVICEID"]
    if os.environ.get("YOUPIN_DEVICEUK"):
        h["deviceuk"] = os.environ["YOUPIN_DEVICEUK"]
    if os.environ.get("YOUPIN_UK"):
        h["uk"] = os.environ["YOUPIN_UK"]
    # fresh per-request tracing IDs (the real site sends these; missing them
    # can trigger an anti-bot 429 "too frequent" response)
    trace = uuid.uuid4().hex
    span = uuid.uuid4().hex[:16]
    h["b3"] = f"{trace}-{span}-1"
    h["traceparent"] = f"00-{trace}-{span}-01"
    h["priority"] = "u=1, i"
    return h


def keyword_of(market_hash_name: str) -> str:
    """Strip star / StatTrak / Souvenir / (wear) / pipe to a broad search
    keyword. Youpin's search chokes on the "|" character, so remove it."""
    s = market_hash_name.replace("★", " ")
    s = re.sub(r"^\s*StatTrak(™)?\s*", "", s)
    s = re.sub(r"^\s*Souvenir\s*", "", s)
    s = re.sub(r"\s*\([^)]+\)\s*$", "", s)   # drop trailing (Wear)
    s = s.replace("|", " ")                     # Youpin search dislikes the pipe
    return re.sub(r"\s+", " ", s).strip()


def _finish_word(market_hash_name: str) -> str:
    """The finish part after the pipe, e.g. 'Autotronic' — a distinctive
    fallback keyword when the full name returns nothing."""
    m = re.search(r"\|\s*([^(]+?)\s*(?:\([^)]*\))?\s*$", market_hash_name)
    return m.group(1).strip() if m else ""


def _weapon_word(market_hash_name: str) -> str:
    """The weapon part before the pipe, without star/prefixes/'Knife' noun that
    Youpin's search dislikes, e.g. '★ Navaja Knife | Stained' -> 'Navaja'."""
    before = market_hash_name.split("|")[0] if "|" in market_hash_name else market_hash_name
    before = before.replace("★", " ")
    before = re.sub(r"\b(StatTrak(™)?|Souvenir)\b", " ", before)
    before = re.sub(r"\bKnife\b", " ", before)
    return re.sub(r"\s+", " ", before).strip()


def _keywords(market_hash_name: str) -> list[str]:
    """Ordered, de-duplicated search terms to try. Dropping the word 'Knife'
    matters: Youpin returns nothing for 'Navaja Knife Stained' but works for
    'Navaja Stained'."""
    full = keyword_of(market_hash_name)
    no_knife = re.sub(r"\s+", " ", re.sub(r"\bKnife\b", " ", full)).strip()
    weapon = _weapon_word(market_hash_name)
    finish = _finish_word(market_hash_name)
    combo = f"{weapon} {finish}".strip() if (weapon and finish) else ""
    out = []
    for k in (full, no_knife, combo, finish):
        if k and k not in out:
            out.append(k)
    return out


def _norm(s: str) -> str:
    s = (s or "").replace("★", " ").replace("™", " ").replace("|", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def _strip_wear(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", name or "").strip()


# Youpin has renamed/nested these fields across app versions — try them all.
_NAME_KEYS = ("commodityHashName", "templateHashName", "hashName",
              "marketHashName", "commodityName", "templateName", "name")
_PRICE_KEYS = ("price", "minSellPrice", "templateSellPrice", "sellPrice",
               "minPrice", "referencePrice")
_ID_KEYS = ("id", "templateId", "goodsId", "commodityTemplateId")
_LIST_KEYS = ("dataList", "commodityTemplateList", "templateList", "list",
              "saleTemplateList", "records", "items", "rows")


def extract_rows(response) -> list:
    """Pull the row list out of the response, tolerating shape changes:
    Data/data as a list, or a dict wrapping the list under a known key."""
    if not isinstance(response, dict):
        return []
    node = response.get("Data", response.get("data"))
    if isinstance(node, list):
        return node
    if isinstance(node, dict):
        for k in _LIST_KEYS:
            v = node.get(k)
            if isinstance(v, list):
                return v
        # single nested dict? descend one level looking for any list of dicts
        for v in node.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def _row_name(r) -> str:
    for k in _NAME_KEYS:
        v = r.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _row_price(r):
    for k in _PRICE_KEYS:
        if r.get(k) is not None:
            p = _to_float(r.get(k))
            if p is not None:
                return p
    return None


def _row_id(r):
    for k in _ID_KEYS:
        if r.get(k) is not None:
            return r.get(k)
    return None


def match_price(response: dict, target_mhn: str):
    """Return (price_cny, id) for the row matching target_mhn.

    Tiers: exact name -> normalized full name -> if the target has no (wear),
    the cheapest row sharing the same base (respecting StatTrak/Souvenir, which
    survive normalization as words)."""
    rows = extract_rows(response)
    if not rows:
        return None, None

    # 1) exact
    for r in rows:
        if _row_name(r) == target_mhn:
            return _row_price(r), _row_id(r)

    # 2) normalized full name (handles star/™/pipe/spacing differences)
    tgt = _norm(target_mhn)
    for r in rows:
        if _norm(_row_name(r)) == tgt:
            return _row_price(r), _row_id(r)

    # 2.5) loose: also ignore parentheses/hyphens ("(Field-Tested)" vs
    # "Field Tested" formatting drift)
    loose = re.sub(r"[()\-]", " ", tgt)
    loose = re.sub(r"\s+", " ", loose).strip()
    for r in rows:
        rn = re.sub(r"[()\-]", " ", _norm(_row_name(r)))
        rn = re.sub(r"\s+", " ", rn).strip()
        if rn == loose:
            return _row_price(r), _row_id(r)

    # 3) target has no (wear) -> cheapest row whose base matches
    if not re.search(r"\([^)]*\)\s*$", target_mhn):
        base = _norm(_strip_wear(target_mhn))
        cands = []
        for r in rows:
            if _norm(_strip_wear(_row_name(r))) == base:
                pr = _row_price(r)
                if pr is not None:
                    cands.append((pr, _row_id(r)))
        if cands:
            return min(cands, key=lambda t: t[0])

    return None, None


def _to_float(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


# populated by _post so callers/debug can see the last failure reason
_last_error = None


def _post(keyword: str):
    """Return the parsed response dict, or None. Records _last_error."""
    global _last_error
    body = {
        "keyWords": keyword,
        "listSortType": 0,
        "sortType": 0,
        "gameId": 730,
        "filterMap": {},
        "pageSize": 50,
        "pageIndex": 1,
    }
    data = json.dumps(body).encode("utf-8")
    for attempt in range(2):  # one retry on 429
        _throttle()
        req = urllib.request.Request(API, data=data, headers=_headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            code = payload.get("Code", payload.get("code"))
            if code not in (0, None):
                _last_error = f"Code {code}: {payload.get('Msg') or payload.get('msg')}"
            return payload
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:200]
            except Exception:
                pass
            _last_error = f"HTTP {exc.code} {detail}"
            if exc.code == 429 and attempt == 0:
                time.sleep(3.0)   # back off, then retry once
                continue
            return None
        except (urllib.error.URLError, ValueError) as exc:
            _last_error = f"{type(exc).__name__}: {exc}"
            return None
    return None


def price_for(market_hash_name: str) -> dict:
    global _last_error
    ck = f"yp:{market_hash_name.lower().strip()}"
    hit = _cache.get(ck)
    if hit and (time.time() - hit[0]) < CACHE_TTL:
        return hit[1]

    _last_error = None  # don't leak a stale error from a previous item
    price, tid = None, None
    rows_seen = 0
    sample = []
    for kw in _keywords(market_hash_name):
        resp = _post(kw)
        if resp is None:
            break  # network/429/auth error — don't keep hammering
        rows = extract_rows(resp)
        rows_seen = max(rows_seen, len(rows))
        if rows and not sample:
            sample = [_row_name(r) for r in rows[:3]]
        price, tid = match_price(resp, market_hash_name)
        if price is not None:
            break

    result = {
        "price_cny": price,
        "online": price is not None,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "url": f"https://www.youpin898.com/goodInfo?id={tid}" if tid else "https://www.youpin898.com/",
    }
    if price is None:
        if _last_error:
            result["error"] = _last_error
        elif rows_seen == 0:
            result["error"] = "no rows returned (search empty or response shape changed)"
        else:
            result["error"] = (
                f"no match among {rows_seen} rows; sample: {sample}"
            )
    if price is not None:  # never cache failures — retry next click
        _cache[ck] = (time.time(), result)
    return result


def debug(market_hash_name: str) -> dict:
    """Diagnostic: show exactly what Youpin returns for a name, including the
    raw response shape so parsing drift is obvious."""
    global _last_error
    _last_error = None
    kw = keyword_of(market_hash_name)
    resp = _post(kw)
    rows = extract_rows(resp) if resp else []
    sample = [_row_name(r) for r in rows[:8]]
    price, tid = (match_price(resp, market_hash_name) if resp else (None, None))
    out = {
        "keyword_sent": kw,
        "keywords_tried_in_order": _keywords(market_hash_name),
        "target": market_hash_name,
        "last_error": _last_error,
        "rows_returned": len(rows),
        "sample_names": sample,
        "matched_price_cny": price,
        "auth_present": bool(os.environ.get("YOUPIN_AUTHORIZATION")),
    }
    if isinstance(resp, dict):
        out["response_top_level_keys"] = list(resp.keys())
        out["response_code"] = resp.get("Code", resp.get("code"))
        out["response_msg"] = resp.get("Msg", resp.get("msg"))
        node = resp.get("Data", resp.get("data"))
        out["data_node_type"] = type(node).__name__
        if isinstance(node, dict):
            out["data_node_keys"] = list(node.keys())
        if rows and isinstance(rows[0], dict):
            out["first_row_keys"] = list(rows[0].keys())
    return out


# A spread of popular guns + knives (various finishes/wears) to prove Youpin
# works broadly, not one item at a time.
_SELFTEST_ITEMS = [
    "AK-47 | Redline (Field-Tested)",
    "AWP | Asiimov (Field-Tested)",
    "M4A4 | Asiimov (Field-Tested)",
    "M4A1-S | Hyper Beast (Field-Tested)",
    "USP-S | Kill Confirmed (Minimal Wear)",
    "Glock-18 | Fade (Factory New)",
    "Desert Eagle | Blaze (Factory New)",
    "AWP | Neo-Noir (Field-Tested)",
    "AK-47 | Asiimov (Field-Tested)",
    "AWP | Dragon Lore (Field-Tested)",
    "★ Karambit | Doppler (Factory New)",
    "★ M9 Bayonet | Fade (Factory New)",
    "★ Butterfly Knife | Fade (Factory New)",
    "★ Karambit | Night (Factory New)",
    "★ Flip Knife | Marble Fade (Factory New)",
]


def selftest() -> dict:
    """Query Youpin for each test item; report matched vs failed with reasons."""
    global _last_error
    results = []
    matched = 0
    for name in _SELFTEST_ITEMS:
        _last_error = None
        _cache.pop(f"yp:{name.lower().strip()}", None)
        r = price_for(name)
        ok = r.get("price_cny") is not None
        matched += 1 if ok else 0
        results.append({
            "name": name,
            "price_cny": r.get("price_cny"),
            "reason": None if ok else (r.get("error") or "no matching row"),
        })
    return {
        "matched": matched,
        "tested": len(_SELFTEST_ITEMS),
        "auth_present": bool(os.environ.get("YOUPIN_AUTHORIZATION")),
        "results": results,
    }
