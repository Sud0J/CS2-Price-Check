"""Local per-minute price runner.

Runs on YOUR machine (residential IP + your logged-in Buff cookie), which is the
only cost-free way to get Buff163/Youpin898 to answer reliably — cloud IPs
(GitHub Actions, Cloudflare) get blocked by their anti-bot.

Every REFRESH_SECONDS it:
  1. runs the Buff163 + Youpin898 fetchers (add csfloat/c5game via ALL_SOURCES)
  2. runs merge.py to rebuild public/data/prices.json
  3. refreshes rates.json every RATES_EVERY cycles

Secrets are read from scripts/.secrets.env (git-ignored). Never commit it.
Example file: scripts/.secrets.env.example

Usage:
    cd scripts
    cp .secrets.env.example .secrets.env   # then paste your BUFF_COOKIE
    python live_runner.py                   # Ctrl-C to stop

Frontend: serve /public (or `npm run dev`) and it will poll prices.json.

WARNING: per-minute polling multiplies requests by the number of tracked
variants. A big Doppler list WILL get you rate-limited/banned on Buff. Keep
items.json small (tune KNIVES/GUNS in gen_items.py).
"""

from __future__ import annotations

import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "60"))
RATES_EVERY = int(os.environ.get("RATES_EVERY", "60"))  # ~ once/hour at 60s
# Priority sources per the build order. Add "csfloat", "c5game" if wanted.
ACTIVE_SOURCES = os.environ.get("ACTIVE_SOURCES", "buff163,youpin898").split(",")


def load_secrets() -> None:
    """Load KEY=VALUE lines from scripts/.secrets.env into os.environ."""
    f = HERE / ".secrets.env"
    if not f.exists():
        print("! No scripts/.secrets.env found. Buff163 will likely be blocked "
              "without BUFF_COOKIE. Copy .secrets.env.example to get started.")
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ[key.strip()] = val.strip().strip('"').strip("'")
    print("loaded secrets from .secrets.env")


def run_script(rel_path: str) -> None:
    """Run a fetcher/merge script in a child process so a crash is isolated."""
    try:
        subprocess.run([sys.executable, rel_path], cwd=HERE, check=False, timeout=300)
    except subprocess.TimeoutExpired:
        print(f"  ! {rel_path} timed out")


def main() -> None:
    load_secrets()
    print(f"live runner: every {REFRESH_SECONDS}s | sources={ACTIVE_SOURCES}")
    cycle = 0
    while True:
        start = time.time()
        print(f"\n=== cycle {cycle} @ {time.strftime('%H:%M:%S')} ===")
        for src in ACTIVE_SOURCES:
            src = src.strip()
            if src:
                run_script(f"fetchers/{src}.py")
        run_script("merge.py")
        if cycle % RATES_EVERY == 0:
            run_script("fetch_rates.py")
        cycle += 1

        elapsed = time.time() - start
        sleep_for = max(0, REFRESH_SECONDS - elapsed)
        print(f"cycle took {elapsed:.1f}s; sleeping {sleep_for:.1f}s")
        try:
            time.sleep(sleep_for)
        except KeyboardInterrupt:
            print("\nstopped.")
            break


if __name__ == "__main__":
    main()
