# CS2 Multi-Platform Price Checker

Search a CS2 skin, pick a specific condition/variant, and get **live** prices
from Buff163 (and Youpin898 / CSFloat once configured), converted into USDT,
USD, VND, CNY, or EUR.

Prices are fetched **on demand** — only for the exact item you pick. Nothing is
polled in the background, so you won't get rate-limited or banned.

## Why there's a local server

Browsers can't call Buff163/Youpin directly: it would leak your login cookie and
their servers block browser cross-origin requests. Those marketplaces also block
datacenter IPs (GitHub Actions, Cloudflare). So a tiny **local Python server runs
on your machine**, holds your Buff cookie, uses your home/residential IP, and
fetches a price only when you click a skin. This is the only cost-free way to get
reliable Buff/Youpin pricing.

```
Browser (React)  ──/api/search?q=ak──►  server.py  ──►  Buff163 (your cookie, your IP)
                 ◄── finishes+prices ──            ◄──
                 ──/api/price?goods_id──►          ──►  Buff163 sell orders (cached ~60s)
```

## Setup (one time)

```bash
npm install
npm run build          # builds the React frontend into dist/
```

**No Python packages required** — the server uses only Python's standard library,
so `python server.py` works without any `pip install`.

Your Buff cookie is already saved in `scripts/.secrets.env` (git-ignored). To
change it: log in at buff.163.com → DevTools → Application → Cookies →
`buff.163.com` → copy the `session` value into that file.

## Run

```bash
python server.py                 # LIVE — uses your Buff cookie, serves http://localhost:8000
# or preview the UI with fake data, no network:
python server.py --mock
```

Open **http://localhost:8000**, type a skin (e.g. `ak`, `awp asiimov`,
`karambit doppler`), click a finish, then pick a condition/variant to see the
live price. Change display currency in the top-right.

Dev mode (hot reload) — run both:

```bash
python server.py            # terminal 1 (the API on :8000)
npm run dev                 # terminal 2 (Vite on :5173, proxies /api to :8000)
```

## Adding Youpin898 and CSFloat

The price panel already has slots for both; they light up once wired:

- **Youpin898** — already wired (`scripts/youpin_client.py`), best-effort. If it
  shows "blocked/err" in the panel, capture the real request (DevTools → Network
  → Fetch/XHR → do a search → Copy as cURL) and send it so the endpoint/token are
  exact; drop any auth token into `.secrets.env` as `YOUPIN_TOKEN`.
- **CSFloat** — grab a free API key (csfloat.com → profile → Developer tab) and
  put `CSFLOAT_API_KEY="..."` in `scripts/.secrets.env`.

## Trade link checker

The **Trade link** tab prices a whole trade at once:

1. Paste a trade link (`https://steamcommunity.com/tradeoffer/new/?partner=…&token=…`)
   and hit **Load items**.
2. Tick the items in the trade (use +/− for stacks, or Select all).
3. Hit **Show total price** — each item's live price on every site appears,
   converted to your currency, plus per-site totals and a "cheapest mix" total
   (best price per item). Prices are fetched one at a time to avoid rate limits.

Items are read through the **Steam trade window** endpoint, not the public
inventory — the public one hides recently traded items for ~10 days, while the
trade window shows them as soon as the 7-day trade protection ends. That
endpoint needs your Steam login cookies in `scripts/.secrets.env`:

```
STEAM_SESSIONID="..."        # cookie `sessionid` on steamcommunity.com
STEAM_LOGIN_SECURE="..."     # cookie `steamLoginSecure`
```

Get them: log in at steamcommunity.com → DevTools → Application → Cookies →
`https://steamcommunity.com`. Without them the checker falls back to the public
inventory (and tells you so).

## Actual conversion rates

The bar under the header shows the exact numbers in use (from `/api/rates`,
cached ~10 min): **USDT → VND** from Binance P2P *sell* adverts (this single
number drives every VND figure, and USD = USDT 1:1), the official USD → VND
rate for reference, and VND → USDT per 1,000,000₫. Green chips = rates the app
actually converts with.

## Doppler / Gamma Doppler phases

Phase (Phase 1–4, Ruby, Sapphire, Black Pearl, Emerald) is a **knife-only** paint
attribute and is **not** part of the Steam item name — so name-based sources
can't tell phases apart. Phase-accurate prices come only from Buff/Youpin phase
listings. Buff search returns each phase as its own item, so picking a specific
phase works once you search a Doppler knife.

## Files

```
server.py                  # local API + static server (run this)
scripts/
  buff_client.py           # live Buff search + price + name parser
  .secrets.env             # your cookie (git-ignored)
  .secrets.env.example     # template
src/
  App.jsx                  # search box, results, currency
  components/
    FinishList.jsx         # grouped finishes -> wear/variant chips
    PricePanel.jsx         # live price per source for the picked variant
  lib/currency.js          # conversion + formatting
public/data/rates.json     # cached FX + USDT/VND rate
```

### Currency rates

`/api/rates` is computed live by the server (cached ~10 min): fiat via
Frankfurter, and the **USDT/VND rate from Binance P2P *sell* adverts**
(`scripts/rates_client.py`). No action needed.

## Optional: background watchlist mode

The repo also keeps the older snapshot pipeline (`scripts/fetchers/*`,
`merge.py`, `live_runner.py`, GitHub Actions) if you ever want a fixed watchlist
refreshed on a schedule instead of on-demand search. Not needed for normal use.

## Notes

- Prices are cached ~60s per item. Not affiliated with Valve or any marketplace.
- Your Buff cookie is a login secret; it stays local and is never committed.
  Rotate it by logging out/in on Buff if needed.
