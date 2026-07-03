"""Generate scripts/items.json — the tracked-item list, variant-aware.

Each row is ONE tracked variant:
  {
    "item_name": "★ Karambit | Doppler",
    "category":  "knife" | "gun",
    "wear":      "Factory New" | ... ,
    "stattrak":  true/false,
    "souvenir":  true/false,
    "phase":     null | "Phase 1".."Phase 4" | "Ruby" | "Sapphire"
                 | "Black Pearl" | "Emerald"
  }

IMPORTANT design notes:
- Doppler / Gamma Doppler are KNIFE-ONLY finishes. There are no Doppler guns.
- Phase is NOT part of the Steam market_hash_name; it is a paint attribute.
  Steam/CSFloat name lookups cannot tell phases apart. Phase-accurate prices
  come only from Buff/Youpin phase-specific listings, so `phase` here is used
  for display and for phase-aware queries once those sources are wired.
- Per-minute polling multiplies request volume by the number of rows. Keep the
  KNIVES / GUNS lists SMALL to avoid Buff/Youpin anti-bot bans. Expand
  deliberately.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- Tune these lists. Small on purpose. ---------------------------------
KNIVES = ["★ Karambit", "★ M9 Bayonet"]          # add more knife bases here
KNIFE_WEARS = ["Factory New"]                     # Dopplers usually FN/MW

DOPPLER_PHASES = ["Phase 1", "Phase 2", "Phase 3", "Phase 4",
                  "Ruby", "Sapphire", "Black Pearl"]
GAMMA_PHASES = ["Phase 1", "Phase 2", "Phase 3", "Phase 4", "Emerald"]

# Guns: (name, [wears], souvenir_capable)
GUNS = [
    ("AK-47 | Redline",        ["Field-Tested", "Minimal Wear"], False),
    ("AWP | Asiimov",          ["Field-Tested"],                 False),
    ("M4A4 | Howl",            ["Field-Tested"],                 False),
    ("USP-S | Kill Confirmed", ["Minimal Wear"],                 False),
    ("Desert Eagle | Blaze",   ["Factory New"],                  False),
    ("Glock-18 | Fade",        ["Factory New"],                  False),
    ("AWP | Dragon Lore",      ["Field-Tested"],                 True),  # souvenir exists
    ("AK-47 | Asiimov",        ["Field-Tested"],                 False),
]
# -------------------------------------------------------------------------


def knife_rows() -> list[dict]:
    rows = []
    for base in KNIVES:
        for wear in KNIFE_WEARS:
            # Doppler
            for phase in DOPPLER_PHASES:
                for st in (False, True):
                    rows.append({
                        "item_name": f"{base} | Doppler",
                        "category": "knife", "wear": wear,
                        "stattrak": st, "souvenir": False, "phase": phase,
                    })
            # Gamma Doppler
            for phase in GAMMA_PHASES:
                for st in (False, True):
                    rows.append({
                        "item_name": f"{base} | Gamma Doppler",
                        "category": "knife", "wear": wear,
                        "stattrak": st, "souvenir": False, "phase": phase,
                    })
    return rows


def gun_rows() -> list[dict]:
    rows = []
    for name, wears, souv in GUNS:
        for wear in wears:
            rows.append({"item_name": name, "category": "gun", "wear": wear,
                         "stattrak": False, "souvenir": False, "phase": None})
            # StatTrak variant (skip knives-only logic; guns can be ST if not souvenir)
            rows.append({"item_name": name, "category": "gun", "wear": wear,
                         "stattrak": True, "souvenir": False, "phase": None})
            if souv:
                rows.append({"item_name": name, "category": "gun", "wear": wear,
                             "stattrak": False, "souvenir": True, "phase": None})
    return rows


def main() -> None:
    items = gun_rows() + knife_rows()
    (ROOT / "items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    knives = sum(1 for i in items if i["category"] == "knife")
    guns = len(items) - knives
    print(f"wrote items.json: {len(items)} variants ({guns} gun rows, {knives} knife rows)")
    print("Tune KNIVES/GUNS lists to control per-minute request volume.")


if __name__ == "__main__":
    main()
