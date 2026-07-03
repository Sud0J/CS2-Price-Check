"""Merge all per-source raw files into public/data/prices.json.

Reads scripts/data_raw/<source>.json (whichever exist), keys every record by
its variant identity (name + wear + stattrak + souvenir + phase), and emits one
row per variant with a `sources` block the frontend expects.

Missing sources are still represented (online: false) so the UI is honest.
"""

from __future__ import annotations

import json

from common import (
    PUBLIC_DATA_DIR,
    RAW_DIR,
    TRACKED_ITEMS,
    now_iso,
    variant_key,
)

SOURCES = ["csfloat", "buff163", "youpin898", "c5game"]
EXPERIMENTAL = {"c5game"}

# Steam CDN image hashes (hotlinked, zero-cost). Optional; unknown -> null.
IMAGE_HASHES = {
    "AK-47 | Redline": "-9a8dkGLuVMBjhcSC3XjhV6xjZ3JZ2GRTAcpsvbF1XZuBSQBWTGtOxTMEP7bWH_ny2XCq6dPzBSg9DUmRSSb51V-tVQfR_-BFqLA",
}
CDN = "https://community.cloudflare.steamstatic.com/economy/image/"


def load_source(source: str) -> dict:
    """Return {variant_key: record} for a source, or {} if absent."""
    path = RAW_DIR / f"{source}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {variant_key(rec): rec for rec in data.get("records", [])}


def image_for(item_name: str) -> str | None:
    h = IMAGE_HASHES.get(item_name)
    return f"{CDN}{h}" if h else None


def main() -> None:
    loaded = {src: load_source(src) for src in SOURCES}

    rows = []
    for item in TRACKED_ITEMS:
        key = variant_key(item)
        sources_block = {}
        for src in SOURCES:
            rec = loaded[src].get(key)
            online = bool(rec and rec.get("online") and rec.get("price") is not None)
            entry = {
                "price": rec.get("price") if rec else None,
                "currency": rec.get("currency") if rec else None,
                "online": online,
                "last_updated": rec.get("last_updated") if rec else None,
                "url": rec.get("url") if rec else None,
            }
            if src in EXPERIMENTAL:
                entry["experimental"] = True
            sources_block[src] = entry

        rows.append({
            "item_name": item["item_name"],
            "category": item.get("category", "gun"),
            "wear": item.get("wear"),
            "stattrak": item.get("stattrak", False),
            "souvenir": item.get("souvenir", False),
            "phase": item.get("phase"),
            "image": image_for(item["item_name"]),
            "sources": sources_block,
        })

    out = {"generated_at": now_iso(), "items": rows}
    dest = PUBLIC_DATA_DIR / "prices.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"merged {len(rows)} variants -> {dest}")


if __name__ == "__main__":
    main()
