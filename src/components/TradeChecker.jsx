import { useRef, useState } from 'react'
import { convertFromUsd, formatPrice } from '../lib/currency.js'

const SOURCES = [
  { key: 'buff163', label: 'Buff163' },
  { key: 'youpin898', label: 'Youpin898' },
  { key: 'csfloat', label: 'CSFloat' },
]

// Same conversion rule as PricePanel: CNY shows the source's native yuan,
// everything else goes through the source's USD anchor.
function sourceValue(src, currency, rates) {
  if (!src || !src.online) return null
  if (currency === 'CNY' && src.price_cny != null) return src.price_cny
  return convertFromUsd(src.price_usd, currency, rates)
}

function friendlyError(src) {
  const e = String(src?.error || '')
  if (!e) return '—'
  if (/429|too frequent/i.test(e)) return 'rate-limited'
  if (/401|403|token|unauthor/i.test(e)) return 'login expired'
  if (/no rows|no match|no matching|no name|no buy-now/i.test(e)) return 'not listed'
  if (/no sell price|no live sell/i.test(e)) return 'no sellers'
  if (/api key rejected|no api key/i.test(e)) return 'needs key'
  if (/refused|login required/i.test(e)) return 'Buff login expired'
  if (/URLError|network|timeout|timed out/i.test(e)) return 'network error'
  return 'error'
}

const TRADE_RE = /steamcommunity\.com\/tradeoffer\/new\/\?.*partner=\d+/i

export default function TradeChecker({ currency, rates }) {
  const [link, setLink] = useState('')
  const [inv, setInv] = useState(null)
  const [invState, setInvState] = useState('idle') // idle|loading|ready|error
  const [invError, setInvError] = useState(null)
  const [qty, setQty] = useState({})        // market_hash_name -> selected qty
  const [prices, setPrices] = useState({})  // market_hash_name -> {state, data}
  const [fetching, setFetching] = useState(false)
  const [progress, setProgress] = useState(null) // {done, total}
  const [showTotals, setShowTotals] = useState(false)
  const runId = useRef(0)

  const linkValid = TRADE_RE.test(link.trim()) || /^\d{5,}$/.test(link.trim())

  async function loadInventory() {
    setInvState('loading')
    setInv(null)
    setQty({})
    setPrices({})
    setShowTotals(false)
    runId.current += 1
    try {
      const r = await fetch(`/api/trade_inventory?link=${encodeURIComponent(link.trim())}`)
      const d = await r.json()
      if (d.error) throw new Error(d.error)
      setInv(d)
      setInvState('ready')
      setInvError(null)
    } catch (e) {
      setInvState('error')
      setInvError(e.message)
    }
  }

  const items = inv?.items || []
  const selectedNames = items.filter((it) => (qty[it.market_hash_name] || 0) > 0)
  const selectedCount = selectedNames.reduce((n, it) => n + qty[it.market_hash_name], 0)

  function setItemQty(name, n, max) {
    setQty((q) => ({ ...q, [name]: Math.max(0, Math.min(max, n)) }))
    setShowTotals(false)
  }

  function toggle(it) {
    const n = qty[it.market_hash_name] || 0
    setItemQty(it.market_hash_name, n > 0 ? 0 : it.count, it.count)
  }

  function selectAll(on) {
    const q = {}
    if (on) for (const it of items) q[it.market_hash_name] = it.count
    setQty(q)
    setShowTotals(false)
  }

  // Fetch prices for selected names, one at a time (Buff/Youpin rate limits).
  async function fetchPrices() {
    const names = selectedNames
      .map((it) => it.market_hash_name)
      .filter((n) => prices[n]?.state !== 'ready')
    setFetching(true)
    setShowTotals(true)
    const me = ++runId.current
    setProgress({ done: 0, total: names.length })
    for (let i = 0; i < names.length; i++) {
      const name = names[i]
      setPrices((p) => ({ ...p, [name]: { state: 'loading' } }))
      try {
        const r = await fetch(`/api/price?${new URLSearchParams({ name })}`)
        const d = await r.json()
        if (runId.current !== me) return
        if (d.error) throw new Error(d.error)
        setPrices((p) => ({ ...p, [name]: { state: 'ready', data: d } }))
      } catch (e) {
        if (runId.current !== me) return
        setPrices((p) => ({ ...p, [name]: { state: 'error', error: e.message } }))
      }
      setProgress({ done: i + 1, total: names.length })
      if (i < names.length - 1) await new Promise((res) => setTimeout(res, 400))
    }
    setFetching(false)
  }

  // Per-item best value (min across sources) in the selected currency.
  function itemBest(name) {
    const d = prices[name]?.data
    if (!d) return null
    let best = null
    for (const s of SOURCES) {
      const v = sourceValue(d[s.key], currency, rates)
      if (v != null && (best == null || v < best)) best = v
    }
    return best
  }

  // Totals across the selection.
  const totals = { perSource: {}, missing: {}, best: 0, bestMissing: 0 }
  if (showTotals) {
    for (const s of SOURCES) { totals.perSource[s.key] = 0; totals.missing[s.key] = 0 }
    for (const it of selectedNames) {
      const n = qty[it.market_hash_name]
      const d = prices[it.market_hash_name]?.data
      for (const s of SOURCES) {
        const v = d ? sourceValue(d[s.key], currency, rates) : null
        if (v != null) totals.perSource[s.key] += v * n
        else totals.missing[s.key] += n
      }
      const best = itemBest(it.market_hash_name)
      if (best != null) totals.best += best * n
      else totals.bestMissing += n
    }
  }
  const allPriced = selectedNames.every((it) => prices[it.market_hash_name]?.state === 'ready')

  return (
    <div className="trade">
      <div className="trade-linkbar">
        <input
          className="search trade-input"
          type="text"
          placeholder="Paste a trade link…  https://steamcommunity.com/tradeoffer/new/?partner=…&token=…"
          value={link}
          onChange={(e) => setLink(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && linkValid) loadInventory() }}
        />
        <button
          type="button"
          className="btn-primary"
          disabled={!linkValid || invState === 'loading'}
          onClick={loadInventory}
        >
          {invState === 'loading' ? 'Loading…' : 'Load items'}
        </button>
      </div>
      {!linkValid && link.trim().length > 0 && (
        <p className="notice error">That doesn’t look like a trade link.</p>
      )}

      {invState === 'error' && (
        <p className="notice error">Couldn’t load items: {invError}</p>
      )}

      {invState === 'ready' && (
        <>
          {inv.warning && <p className="notice warn">⚠ {inv.warning}</p>}
          <div className="trade-toolbar">
            <span className="muted">
              {items.length} unique item{items.length === 1 ? '' : 's'} · partner {inv.partner} · via {inv.source === 'trade_window' ? 'trade window' : inv.source}
            </span>
            <div className="trade-toolbar-btns">
              <button type="button" className="refresh" onClick={() => selectAll(true)}>Select all</button>
              <button type="button" className="refresh" onClick={() => selectAll(false)}>Clear</button>
            </div>
          </div>

          {items.length === 0 && <p className="notice">No CS2 items visible for this partner.</p>}

          <div className="trade-grid">
            {items.map((it) => {
              const name = it.market_hash_name
              const n = qty[name] || 0
              const sel = n > 0
              const pr = prices[name]
              return (
                <div key={name} className={`trade-item ${sel ? 'sel' : ''}`}>
                  <button type="button" className="trade-item-main" onClick={() => toggle(it)}>
                    <span className={`trade-check ${sel ? 'on' : ''}`}>{sel ? '✓' : ''}</span>
                    {it.icon_url
                      ? <img className="trade-icon" src={it.icon_url} alt="" loading="lazy" />
                      : <span className="trade-icon ph" />}
                    <span className="trade-item-name">
                      {name}
                      {!it.tradable && <span className="tag tag-hold">trade hold</span>}
                      {it.count > 1 && <span className="tag">×{it.count}</span>}
                    </span>
                  </button>
                  {sel && it.count > 1 && (
                    <div className="trade-qty">
                      <button type="button" onClick={() => setItemQty(name, n - 1, it.count)}>−</button>
                      <span>{n}/{it.count}</span>
                      <button type="button" onClick={() => setItemQty(name, n + 1, it.count)}>+</button>
                    </div>
                  )}
                  {showTotals && sel && (
                    <div className="trade-prices">
                      {pr?.state === 'loading' && <span className="muted"><span className="spinner" />fetching…</span>}
                      {pr?.state === 'error' && <span className="err" title={pr.error}>price failed</span>}
                      {pr?.state === 'ready' && (() => {
                        const best = itemBest(name)
                        return SOURCES.map((s) => {
                          const v = sourceValue(pr.data[s.key], currency, rates)
                          const isBest = v != null && v === best
                          return (
                            <span key={s.key} className={`trade-price ${isBest ? 'best' : ''}`}>
                              <em>{s.label}</em>
                              {v != null
                                ? <>{formatPrice(v, currency)}{n > 1 && <small> ×{n} = {formatPrice(v * n, currency)}</small>}</>
                                : <span className="muted" title={pr.data[s.key]?.error || ''}>{friendlyError(pr.data[s.key])}</span>}
                            </span>
                          )
                        })
                      })()}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {selectedCount > 0 && (
            <div className="trade-footer">
              <button
                type="button"
                className="btn-primary"
                disabled={fetching}
                onClick={fetchPrices}
              >
                {fetching
                  ? `Fetching prices… ${progress ? `${progress.done}/${progress.total}` : ''}`
                  : `Show total price (${selectedCount} item${selectedCount === 1 ? '' : 's'})`}
              </button>

              {showTotals && (
                <div className="trade-totals">
                  {SOURCES.map((s) => (
                    <div key={s.key} className="total-cell">
                      <span className="total-label">{s.label}</span>
                      <span className="total-value">
                        {formatPrice(totals.perSource[s.key] || null, currency)}
                        {totals.missing[s.key] > 0 && (
                          <small className="muted"> ({totals.missing[s.key]} unpriced)</small>
                        )}
                      </span>
                    </div>
                  ))}
                  <div className="total-cell best">
                    <span className="total-label">Cheapest mix</span>
                    <span className="total-value">
                      {allPriced || totals.best > 0 ? formatPrice(totals.best, currency) : '—'}
                      {totals.bestMissing > 0 && (
                        <small className="muted"> ({totals.bestMissing} unpriced)</small>
                      )}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {invState === 'idle' && (
        <div className="empty">
          <h2>Price a whole trade at once</h2>
          <p className="muted">
            Paste a Steam trade link. Items are read through the trade window
            (with your Steam cookies in <code>scripts/.secrets.env</code>), so
            recently traded items that public inventories hide still show up.
            Tick the items in the trade, then hit the button to fetch each
            item’s live price on every site plus the total.
          </p>
        </div>
      )}
    </div>
  )
}
