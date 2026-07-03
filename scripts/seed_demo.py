"""Generate realistic *demo* data_raw/*.json across all tracked variants so the
committed site renders live-looking prices before real fetchers run. These are
approximations, NOT real quotes — replaced the moment live_runner / Actions
pulls real data. Prices modelled from a base value x variant multipliers."""
import json
from common import RAW_DIR, TRACKED_ITEMS, now_iso, variant_key, market_hash_name

# Base USD price for guns (normal, base wear). ST/Souvenir applied via multiplier.
GUN_BASE_USD = {
    "AK-47 | Redline": 8.0, "AWP | Asiimov": 55.0, "M4A4 | Howl": 1420.0,
    "USP-S | Kill Confirmed": 44.0, "Desert Eagle | Blaze": 452.0,
    "Glock-18 | Fade": 263.0, "AWP | Dragon Lore": 9100.0, "AK-47 | Asiimov": 71.0,
}
# Base USD for knife Doppler (normal, Phase base). Phase/gem multipliers below.
KNIFE_BASE_USD = {"★ Karambit": 900.0, "★ M9 Bayonet": 620.0}
PHASE_MULT = {
    "Phase 1": 1.00, "Phase 2": 1.05, "Phase 3": 1.02, "Phase 4": 1.10,
    "Ruby": 2.6, "Sapphire": 3.1, "Black Pearl": 2.2, "Emerald": 8.0, None: 1.0,
}
WEAR_MULT = {"Factory New": 1.0, "Minimal Wear": 0.9, "Field-Tested": 0.8,
             "Well-Worn": 0.7, "Battle-Scarred": 0.6}
USD_CNY = 7.15  # rough, only for demo seed


def base_usd(item):
    if item.get("category") == "knife":
        base = KNIFE_BASE_USD.get(item["item_name"], 500.0)
        if "Gamma" in item["item_name"]:
            base *= 1.15
    else:
        base = GUN_BASE_USD.get(item["item_name"], 20.0)
    base *= PHASE_MULT.get(item.get("phase"), 1.0)
    base *= WEAR_MULT.get(item.get("wear"), 1.0)
    if item.get("stattrak"):
        base *= 1.15
    if item.get("souvenir"):
        base *= 1.4
    return round(base, 2)


def rec(item, price, currency, online, url):
    return {**{k: item.get(k) for k in
               ("item_name", "category", "wear", "stattrak", "souvenir", "phase")},
            "price": price, "currency": currency,
            "online": online and price is not None,
            "last_updated": now_iso(), "url": url}


# Deterministic per-source spread so sources differ slightly but stably.
def spread(key, pct):
    h = sum(ord(c) for c in key) % 100 / 100.0  # 0..1
    return 1 + (h - 0.5) * 2 * pct


buckets = {"csfloat": [], "buff163": [], "youpin898": [], "c5game": []}
for item in TRACKED_ITEMS:
    k = variant_key(item)
    usd = base_usd(item)
    cny = usd * USD_CNY
    mhn = market_hash_name(item)
    # csfloat: USD, name-based (can't see phase) -> for knives leave online but note
    buckets["csfloat"].append(rec(item, round(usd * spread(k + "cf", 0.03), 2),
        "USD", True, f"https://csfloat.com/search?market_hash_name={mhn}"))
    buckets["buff163"].append(rec(item, round(cny * spread(k + "bf", 0.04), 2),
        "CNY", True, "https://buff.163.com/market/csgo"))
    # youpin online for ~85% of variants (demo of offline handling)
    yp_online = (sum(ord(c) for c in k) % 20) != 0
    buckets["youpin898"].append(rec(item, round(cny * spread(k + "yp", 0.04), 2) if yp_online else None,
        "CNY", yp_online, "https://www.youpin898.com/"))
    # c5game experimental: online for ~30%
    c5_online = (sum(ord(c) for c in k) % 10) < 3
    buckets["c5game"].append(rec(item, round(cny * spread(k + "c5", 0.05), 2) if c5_online else None,
        "CNY", c5_online, "https://www.c5game.com/csgo"))

for src, records in buckets.items():
    (RAW_DIR / f"{src}.json").write_text(
        json.dumps({"source": src, "fetched_at": now_iso(), "records": records},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"seeded {src}: {sum(1 for r in records if r['online'])}/{len(records)} online")
