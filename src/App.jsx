import { useEffect, useMemo, useRef, useState } from 'react'
import { CURRENCIES, convert, formatPrice, timeAgo } from './lib/currency.js'
import FinishList from './components/FinishList.jsx'
import PricePanel from './components/PricePanel.jsx'
import TradeChecker from './components/TradeChecker.jsx'
import RatesBar from './components/RatesBar.jsx'

export default function App() {
  const [mode, setMode] = useState('search') // search | trade
  const [query, setQuery] = useState('')
  const [finishes, setFinishes] = useState([])
  const [searchState, setSearchState] = useState('idle') // idle|loading|ready|error
  const [searchError, setSearchError] = useState(null)
  const [openBase, setOpenBase] = useState(null)
  const [selected, setSelected] = useState(null) // a variant object + base
  const [currency, setCurrency] = useState('USD')
  const [rates, setRates] = useState(null)
  const debounce = useRef(null)
  const searchSeq = useRef(0)

  // Load currency rates once.
  useEffect(() => {
    fetch('/api/rates')
      .then((r) => r.json())
      .then(setRates)
      .catch(() => setRates(null))
  }, [])

  // Escape closes the price panel.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setSelected(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Debounced search as the user types.
  useEffect(() => {
    clearTimeout(debounce.current)
    const q = query.trim()
    if (q.length < 2) {
      setFinishes([])
      setSearchState('idle')
      return
    }
    setSearchState('loading')
    debounce.current = setTimeout(async () => {
      const seq = ++searchSeq.current // ignore out-of-date responses
      const ctrl = new AbortController()
      const kill = setTimeout(() => ctrl.abort(), 20000)
      try {
        const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`, { signal: ctrl.signal })
        const data = await r.json()
        if (seq !== searchSeq.current) return
        if (data.error) throw new Error(data.error)
        setFinishes(data.finishes || [])
        setSearchState('ready')
        setSearchError(null)
      } catch (e) {
        if (seq !== searchSeq.current) return
        setSearchState('error')
        setSearchError(e.name === 'AbortError' ? 'timed out after 20s — try again' : e.message)
      } finally {
        clearTimeout(kill)
      }
    }, 350)
    return () => clearTimeout(debounce.current)
  }, [query])

  const convertFn = useMemo(
    () => (amountCny) => convert(amountCny, 'CNY', currency, rates),
    [currency, rates],
  )

  function pickVariant(base, category, variant) {
    setSelected({ base, category, ...variant })
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">CS2</span>
          <div>
            <h1>Price Checker</h1>
            <p className="sub">Search a skin · pick a condition · get live prices</p>
          </div>
        </div>
        <label className="currency">
          Currency
          <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>
      </header>

      <RatesBar rates={rates} />

      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'search'}
          className={`tab ${mode === 'search' ? 'on' : ''}`}
          onClick={() => setMode('search')}
        >
          Search
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'trade'}
          className={`tab ${mode === 'trade' ? 'on' : ''}`}
          onClick={() => setMode('trade')}
        >
          Trade link
        </button>
      </div>

      {mode === 'trade' && <TradeChecker currency={currency} rates={rates} />}

      {mode === 'search' && (<>
      <div className="searchbar">
        <input
          className="search"
          type="search"
          autoFocus
          placeholder="Type a skin…  e.g. ak, awp asiimov, karambit doppler"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpenBase(null)
          }}
        />
        {searchState === 'loading' && <span className="hint">searching…</span>}
        {searchState === 'idle' && query.trim().length < 2 && (
          <span className="hint">type at least 2 letters</span>
        )}
      </div>

      {selected && (
        <PricePanel
          selected={selected}
          currency={currency}
          rates={rates}
          onClose={() => setSelected(null)}
        />
      )}

      <main className="results">
        {searchState === 'loading' && (
          <div className="skeletons" aria-hidden="true">
            {[0, 1, 2, 3, 4].map((i) => <div key={i} className="skeleton" />)}
          </div>
        )}
        {searchState === 'error' && (
          <p className="notice error">
            Search failed: {searchError}. Is the local server running
            (<code>python server.py</code>) and your Buff cookie valid?
          </p>
        )}
        {searchState === 'ready' && finishes.length === 0 && (
          <p className="notice">No skins matched “{query}”.</p>
        )}
        {searchState === 'ready' && finishes.length > 0 && (
          <FinishList
            finishes={finishes}
            openBase={openBase}
            setOpenBase={setOpenBase}
            convertFn={convertFn}
            currency={currency}
            selected={selected}
            onPick={pickVariant}
          />
        )}
        {searchState === 'idle' && query.trim().length < 2 && (
          <div className="empty">
            <h2>Compare live marketplace prices</h2>
            <p className="muted">
              Prices are fetched on demand only for what you pick — nothing is
              polled in the background, so no bans. Try one of these:
            </p>
            <div className="suggestions">
              {['AK-47 Redline', 'AWP Asiimov', 'Karambit Doppler', 'M9 Bayonet Fade', 'Glock Fade', 'Desert Eagle Blaze'].map((s) => (
                <button key={s} type="button" className="suggestion" onClick={() => setQuery(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
      </main>
      </>)}

      <footer className="foot">
        On-demand pricing via your local server. Prices cached ~60s per item.
        Doppler phase pricing comes from Buff/Youpin (Steam names can’t encode
        phase). Not affiliated with Valve or any marketplace.
      </footer>
    </div>
  )
}
