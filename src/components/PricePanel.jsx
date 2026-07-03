import { useEffect, useState } from 'react'
import { convertFromUsd, formatPrice, timeAgo } from '../lib/currency.js'

const SOURCES = [
  { key: 'buff163', label: 'Buff163' },
  { key: 'youpin898', label: 'Youpin898' },
  { key: 'csfloat', label: 'CSFloat' },
]

const PHASE_ORDER = [
  'Phase 1', 'Phase 2', 'Phase 3', 'Phase 4',
  'Ruby', 'Sapphire', 'Black Pearl', 'Emerald',
]
const GEMS = new Set(['Ruby', 'Sapphire', 'Black Pearl', 'Emerald'])

// Turn a raw source error into a short, human reason shown in the panel.
function friendlyError(src) {
  const e = String(src?.error || '')
  if (!e) return 'unavailable'
  if (/429|\u9891\u7e41|too frequent/i.test(e)) return 'rate-limited — wait a few min'
  if (/401|403|token|\u767b\u5f55|\u6388\u6743|unauthor/i.test(e)) return 'login expired — re-capture token'
  if (/no rows returned/i.test(e)) return 'not found on Youpin'
  if (/no match among/i.test(e)) return 'not listed (name mismatch)'
  if (/no matching|no name|no buy-now/i.test(e)) return 'not listed'
  if (/no live sell|no sell price/i.test(e)) return 'no sellers right now'
  if (/api key rejected|no api key/i.test(e)) return 'needs key'
  if (/refused|login required/i.test(e)) return 'Buff login expired'
  if (/URLError|network|timeout|timed out/i.test(e)) return 'network error'
  return 'error'
}

// Every source carries a `price_usd` that IS its USDT amount:
//  - Buff163  : CNY at Buff's own rate
//  - CSFloat  : native USD
//  - Youpin898: CNY at the official/Google rate
// USD = USDT = price_usd. VND = price_usd * Binance P2P sell. CNY shows the
// source's native yuan when present; EUR uses the official cross rate.
function sourceValue(key, src, currency, rates) {
  if (!src || !src.online) return null
  if (currency === 'CNY' && src.price_cny != null) return src.price_cny
  return convertFromUsd(src.price_usd, currency, rates)
}

export default function PricePanel({ selected, currency, rates, onClose }) {
  const [data, setData] = useState(null)
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)
  const [phases, setPhases] = useState(null)
  const [phaseState, setPhaseState] = useState('idle')

  const isDoppler = /doppler/i.test(selected.base || '')

  async function load() {
    setState('loading')
    try {
      const q = new URLSearchParams({ name: selected.market_hash_name || '' })
      if (selected.goods_id) q.set('goods_id', String(selected.goods_id))
      const r = await fetch(`/api/price?${q.toString()}`)
      const d = await r.json()
      if (d.error) throw new Error(d.error)
      setData(d)
      setState('ready')
    } catch (e) {
      setError(e.message)
      setState('error')
    }
  }

  async function loadPhases() {
    if (!isDoppler) return
    setPhaseState('loading')
    try {
      const q = new URLSearchParams({ name: selected.market_hash_name || '' })
      if (selected.goods_id) q.set('goods_id', String(selected.goods_id))
      const r = await fetch(`/api/phases?${q.toString()}`)
      const d = await r.json()
      setPhases(d.phases || {})
      setPhaseState('ready')
    } catch {
      setPhaseState('error')
    }
  }

  useEffect(() => {
    load()
    loadPhases()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected.market_hash_name])

  let bestKey = null
  let bestVal = null
  for (const s of SOURCES) {
    const v = sourceValue(s.key, data?.[s.key], currency, rates)
    if (v == null) continue
    if (bestVal == null || v < bestVal) { bestVal = v; bestKey = s.key }
  }

  const variantLabel = [
    selected.stattrak ? 'StatTrak™' : '',
    selected.souvenir ? 'Souvenir' : '',
    !selected.stattrak && !selected.souvenir ? 'Normal' : '',
    selected.wear || '',
  ].filter(Boolean).join(' · ')

  const phaseKeys = phases ? PHASE_ORDER.filter((p) => phases[p]) : []

  function phaseValue(ph) {
    // Buff phases -> Buff's own USD (or native CNY for CNY display)
    if (currency === 'CNY' && ph.price_cny != null) return ph.price_cny
    return convertFromUsd(ph.price_usd, currency, rates)
  }

  return (
    <section className="panel">
      <button type="button" className="panel-close" onClick={onClose} aria-label="Close">✕</button>
      <div className="panel-head">
        <h2>{selected.base}</h2>
        <p className="panel-variant">{variantLabel}</p>
      </div>

      <div className="panel-sources">
        {SOURCES.map((s) => {
          const src = data?.[s.key]
          const value = sourceValue(s.key, src, currency, rates)
          const isBest = s.key === bestKey && value != null
          return (
            <div key={s.key} className={`panel-src ${isBest ? 'best' : ''}`}>
              <div className="panel-src-label">
                {s.label}
                {isBest && <span className="mini-flag best-flag">cheapest</span>}
                {s.key !== 'youpin898' && value != null && (
                  <span className="mini-flag" title="Shown at this marketplace's own USD rate">own rate</span>
                )}
              </div>
              <div className="panel-src-price">
                {state === 'loading' ? (
                  <span className="muted"><span className="spinner" />fetching…</span>
                ) : value != null ? (
                  formatPrice(value, currency)
                ) : (
                  <span className="muted" title={src?.error || ''}>
                    {friendlyError(src)}
                  </span>
                )}
              </div>
              {state === 'ready' && src?.online && src.updated && (
                <a className="panel-src-sub" href={src.url} target="_blank" rel="noreferrer">
                  {timeAgo(src.updated)} · view →
                </a>
              )}
              {state === 'ready' && value == null && src?.error && (
                <div className="panel-src-err">{String(src.error).slice(0, 160)}</div>
              )}
            </div>
          )
        })}
      </div>

      {isDoppler && (
        <div className="phases">
          <div className="phases-head">
            Doppler phases <span className="muted">— lowest live Buff listing per phase (Buff rate)</span>
          </div>
          {phaseState === 'loading' && <span className="muted">reading phases…</span>}
          {phaseState === 'ready' && phaseKeys.length === 0 && (
            <span className="muted">No phases in the current cheapest listings — try Refresh.</span>
          )}
          {phaseKeys.length > 0 && (
            <div className="phase-grid">
              {phaseKeys.map((p) => {
                const v = phaseValue(phases[p])
                return (
                  <div key={p} className={`phase-cell ${GEMS.has(p) ? 'gem' : ''}`}>
                    <span className="phase-name">{p}</span>
                    <span className="phase-price">{v != null ? formatPrice(v, currency) : '—'}</span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      <div className="panel-foot">
        {state === 'error' ? (
          <span className="err">{error}</span>
        ) : (
          <span className="muted">
            USD = USDT. VND = USDT × Binance P2P sell. Buff/CSFloat use their own USD rate; Youpin uses the official rate.
          </span>
        )}
        <button type="button" className="refresh" onClick={() => { load(); loadPhases() }} disabled={state === 'loading'}>
          ↻ Refresh
        </button>
      </div>
    </section>
  )
}
