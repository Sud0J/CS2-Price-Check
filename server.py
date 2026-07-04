"""Local price server for the CS2 checker — RUN THIS ON YOUR OWN MACHINE.

Standard library only: no pip installs needed. Browsers can't call
Buff163/Youpin directly (CORS + cookie leak) and those sites block datacenter
IPs, so this runs locally with your cookie + home IP and fetches a price only
when you pick a skin.

  1. npm install && npm run build        # build the frontend into dist/
  2. python server.py                     # http://localhost:8000  (or `py server.py`)
  3. open http://localhost:8000

Endpoints:
  GET /api/search?q=ak                         -> finishes + variants
  GET /api/price?goods_id=123&name=<mhn>       -> {buff163, youpin898} prices
  GET /api/rates                               -> FX + Binance-P2P-sell USDT/VND
  GET /api/trade_inventory?link=<trade link>   -> partner's tradable items

Flags: --mock (fake data, no network), --port N (default 8000), --dist DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
DIST = ROOT / "dist"  # default; override with --dist
sys.path.insert(0, str(SCRIPTS))

MOCK = "--mock" in sys.argv


_secrets_mtime = None


def load_secrets() -> None:
    """(Re)load scripts/.secrets.env whenever it changes — no restart needed
    after pasting a new Buff cookie or Youpin token."""
    global _secrets_mtime
    f = SCRIPTS / ".secrets.env"
    if not f.exists():
        return
    mtime = f.stat().st_mtime
    if mtime == _secrets_mtime:
        return
    _secrets_mtime = mtime
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


# ---- mock data (offline preview) -----------------------------------------
_MOCK_FINISHES = {
    "ak": ["AK-47 | Redline", "AK-47 | Asiimov", "AK-47 | Vulcan"],
    "awp": ["AWP | Asiimov", "AWP | Dragon Lore", "AWP | Neo-Noir"],
    "karambit": ["★ Karambit | Doppler", "★ Karambit | Fade"],
}
_WEARS = ["Factory New", "Minimal Wear", "Field-Tested"]


def _stable(seed: str, lo: float, hi: float) -> float:
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16) % 1000 / 1000.0
    return round(lo + (hi - lo) * h, 2)


def mock_search(q: str):
    q = q.lower().strip()
    bases = next((n for k, n in _MOCK_FINISHES.items() if k in q or q in k), _MOCK_FINISHES["ak"])
    out = []
    for base in bases:
        knife = base.startswith("★")
        variants = []
        for wear in _WEARS:
            for st in (False, True):
                variants.append({
                    "goods_id": abs(hash(base + wear + str(st))) % 100000,
                    "wear": wear, "stattrak": st, "souvenir": False,
                    "label": ("StatTrak™ · " if st else "Normal · ") + wear,
                    "price_cny": _stable(base + wear + str(st),
                                         900 if knife else 60, 4000 if knife else 400),
                    "market_hash_name": base + f" ({wear})",
                })
        out.append({"base": base, "category": "knife" if knife else "gun",
                    "image": None, "variants": variants})
    return out


def mock_price(goods_id: str, name: str):
    buff = _stable(str(goods_id) + "b", 50, 4000)
    yp = round(buff * 0.97, 2)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "buff163": {"price_cny": buff, "price_usd": round(buff / 6.8, 2),
                    "online": True, "updated": now,
                    "url": "https://buff.163.com/market/csgo"},
        "youpin898": {"price_cny": yp, "price_usd": round(yp / 7.2, 2),
                      "online": True, "updated": now,
                      "url": "https://www.youpin898.com/"},
        "csfloat": {"price_usd": round(buff / 7.2, 2), "online": True, "updated": now,
                    "url": "https://csfloat.com"},
    }


def mock_phases(name: str):
    if "doppler" not in name.lower():
        return {"phases": {}}
    base = 2000 if "gamma" not in name.lower() else 2400
    phs = {
        "Phase 1": {"price_cny": round(base * 1.0, 2)},
        "Phase 2": {"price_cny": round(base * 1.15, 2)},
        "Phase 3": {"price_cny": round(base * 1.05, 2)},
        "Phase 4": {"price_cny": round(base * 1.2, 2)},
    }
    if "gamma" in name.lower():
        phs["Emerald"] = {"price_cny": round(base * 8, 2)}
    else:
        phs["Ruby"] = {"price_cny": round(base * 2.6, 2)}
        phs["Sapphire"] = {"price_cny": round(base * 3.1, 2)}
        phs["Black Pearl"] = {"price_cny": round(base * 2.2, 2)}
    return {"phases": phs}


_MOCK_INV_ITEMS = [
    ("AK-47 | Redline (Field-Tested)", 2, True),
    ("AWP | Asiimov (Field-Tested)", 1, True),
    ("★ Karambit | Doppler (Factory New)", 1, True),
    ("Glock-18 | Fade (Factory New)", 1, True),
    ("Desert Eagle | Blaze (Factory New)", 3, True),
    ("USP-S | Kill Confirmed (Minimal Wear)", 1, False),
]


def mock_trade_inventory(link: str):
    import steam_client
    partner, _token = steam_client.parse_trade_link(link)
    items = [{
        "market_hash_name": n, "name": n.split(" (")[0], "type": "Weapon",
        "icon_url": None, "tradable": tr, "marketable": tr, "name_color": None,
        "count": c, "asset_ids": [str(1000 * i + j) for j in range(c)],
    } for i, (n, c, tr) in enumerate(_MOCK_INV_ITEMS)]
    return {"partner": partner, "steamid64": str(steam_client.to_steamid64(partner)),
            "source": "mock", "items": items,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def get_rates():
    if MOCK:
        return {"base": "USD", "rates": {"USD": 1.0, "USDT": 1.0, "EUR": 0.92,
                "CNY": 7.15, "VND": 25400.0}, "usdt_vnd": 25600.0,
                "usdt_vnd_source": "mock"}
    import rates_client
    return rates_client.get_rates()


_CNY_FALLBACK = 7.2


def _official_cny_rate() -> float:
    """USD->CNY official rate from /api/rates (rates_client caches ~10 min)."""
    try:
        r = get_rates()
        v = (r.get("rates") or {}).get("CNY")
        if v:
            return float(v)
    except Exception:
        pass
    return _CNY_FALLBACK


def _live_search(q: str):
    import buff_client
    return buff_client.search(q)


def _live_price(goods_id: str, name: str):
    import buff_client
    import youpin_client
    import csfloat_client
    out = {}
    # Buff: prefer goods_id (fast) else resolve by exact name (covers all wears)
    try:
        if goods_id and goods_id.isdigit():
            out["buff163"] = buff_client.price(int(goods_id))
        elif name:
            out["buff163"] = buff_client.price_by_name(name)
        else:
            out["buff163"] = {"price_cny": None, "online": False, "error": "no id/name"}
    except Exception as exc:
        out["buff163"] = {"price_cny": None, "online": False, "error": str(exc)}
    # Youpin: keyword/name search (best-effort). Youpin's sale price is CNY only
    # (its steamUsdPrice is Steam regional pricing, NOT an FX rate), so convert to
    # USD with the official/Google CNY rate.
    try:
        yp = youpin_client.price_for(name) if name else {
            "price_cny": None, "online": False, "error": "no name"}
        if yp.get("price_cny") is not None:
            yp["price_usd"] = round(yp["price_cny"] / _official_cny_rate(), 2)
        out["youpin898"] = yp
    except Exception as exc:
        out["youpin898"] = {"price_cny": None, "online": False, "error": str(exc)}
    # CSFloat: name-based, USD, only if API key present
    try:
        out["csfloat"] = csfloat_client.price_by_name(name) if name else {
            "price_usd": None, "online": False, "error": "no name"}
    except Exception as exc:
        out["csfloat"] = {"price_usd": None, "online": False, "error": str(exc)}
    return out


def _live_phases(name: str, goods_id: str):
    import buff_client
    gid = goods_id if (goods_id and goods_id.isdigit()) else None
    if gid is None and name:
        gid = (buff_client.price_by_name(name) or {}).get("goods_id")
    if not gid:
        return {"phases": {}, "error": "no goods_id"}
    return {"phases": buff_client.phases(int(gid))}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(DIST), **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # browser gave up waiting — nothing to send it anymore

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self._api(parsed)
        if not (DIST / parsed.path.lstrip("/")).exists() and "." not in Path(parsed.path).name:
            self.path = "/index.html"
        return super().do_GET()

    def _api(self, parsed):
        qs = parse_qs(parsed.query)
        load_secrets()  # pick up an edited .secrets.env without restarting
        try:
            if parsed.path == "/api/search":
                q = (qs.get("q") or [""])[0]
                if not q.strip():
                    return self._json({"error": "missing q"}, 400)
                data = mock_search(q) if MOCK else _live_search(q)
                return self._json({"query": q, "finishes": data})
            if parsed.path == "/api/price":
                gid = (qs.get("goods_id") or [""])[0]
                name = (qs.get("name") or [""])[0]
                if not gid and not name:
                    return self._json({"error": "missing goods_id or name"}, 400)
                data = mock_price(gid, name) if MOCK else _live_price(gid, name)
                return self._json(data)
            if parsed.path == "/api/buff_selftest":
                if MOCK:
                    return self._json({"note": "server is in --mock mode"})
                import buff_client
                return self._json(buff_client.selftest())
            if parsed.path == "/api/buff_selftest":
                if MOCK:
                    return self._json({"note": "server is in --mock mode"})
                import buff_client
                return self._json(buff_client.selftest())
            if parsed.path == "/api/youpin_selftest":
                if MOCK:
                    return self._json({"note": "server is in --mock mode"})
                import youpin_client
                return self._json(youpin_client.selftest())
            if parsed.path == "/api/youpin_debug":
                name = (qs.get("name") or [""])[0]
                if not name:
                    return self._json({"error": "add ?name=<market hash name>"}, 400)
                if MOCK:
                    return self._json({"note": "server is in --mock mode"})
                import youpin_client
                return self._json(youpin_client.debug(name))
            if parsed.path == "/api/phases":
                name = (qs.get("name") or [""])[0]
                gid = (qs.get("goods_id") or [""])[0]
                if not name and not gid:
                    return self._json({"error": "missing name or goods_id"}, 400)
                data = mock_phases(name) if MOCK else _live_phases(name, gid)
                return self._json(data)
            if parsed.path == "/api/trade_inventory":
                link = (qs.get("link") or [""])[0]
                if not link.strip():
                    return self._json({"error": "missing link"}, 400)
                import steam_client
                try:
                    data = (mock_trade_inventory(link) if MOCK
                            else steam_client.trade_inventory(link))
                except steam_client.SteamError as exc:
                    return self._json({"error": str(exc)}, 502)
                return self._json(data)
            if parsed.path == "/api/rates":
                return self._json(get_rates())
        except Exception as exc:
            return self._json({"error": str(exc)}, 502)
        return self._json({"error": "not found"}, 404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--dist", default=None, help="override static dir")
    args = ap.parse_args()

    global DIST
    if args.dist:
        DIST = Path(args.dist).resolve()
    load_secrets()
    if not DIST.exists():
        print("! dist/ not found. Run `npm run build` first.", file=sys.stderr)
    mode = "MOCK (fake data)" if MOCK else "LIVE (Buff163 + Youpin898 via your cookie)"
    if not MOCK and not os.environ.get("BUFF_COOKIE"):
        print("! No BUFF_COOKIE loaded — Buff will likely block requests.", file=sys.stderr)
    print(f"CS2 price server: http://localhost:{args.port}  [{mode}]")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
