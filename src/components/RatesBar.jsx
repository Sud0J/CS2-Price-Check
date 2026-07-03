// Shows the ACTUAL conversion numbers the app is using right now:
//   - USDT -> VND : Binance P2P *sell* price (this drives every VND figure)
//   - USD  -> VND : official fiat rate (reference only — the app converts
//                   USD via USDT, i.e. with the P2P number)
//   - VND  -> USDT/USD : inverse of the P2P sell price
export default function RatesBar({ rates }) {
  if (!rates) return null
  const p2p = rates.usdt_vnd
  const official = rates.rates?.VND
  const fmt = (n) => (n == null ? '—' : Math.round(n).toLocaleString('en-US'))

  return (
    <div className="ratesbar" title={`Source: ${rates.usdt_vnd_source || 'unknown'} · fetched ${rates.generated_at || ''}`}>
      <span className="rate-chip used">
        <em>USDT → VND</em>
        <strong>{fmt(p2p)}₫</strong>
        <small>Binance P2P sell · used for VND</small>
      </span>
      <span className="rate-chip used">
        <em>USD → VND</em>
        <strong>{fmt(p2p)}₫</strong>
        <small>= USDT (1:1) · used</small>
      </span>
      <span className="rate-chip">
        <em>USD → VND</em>
        <strong>{fmt(official)}₫</strong>
        <small>official · reference</small>
      </span>
      <span className="rate-chip used">
        <em>VND → USDT</em>
        <strong>{p2p ? (1000000 / p2p).toFixed(2) : '—'}₮</strong>
        <small>per 1,000,000₫ · 1 ÷ P2P sell · used</small>
      </span>
    </div>
  )
}
