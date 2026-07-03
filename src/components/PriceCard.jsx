import { convert, formatPrice, timeAgo } from '../lib/currency.js'

const SOURCE_LABELS = {
  csfloat: 'CSFloat',
  buff163: 'Buff163',
  youpin898: 'Youpin898',
  c5game: 'C5Game',
}

const SOURCE_ORDER = ['csfloat', 'buff163', 'youpin898', 'c5game']

// Gem phases can't be distinguished by Steam name — only Buff/Youpin phase
// listings can price them; name-based CSFloat lookups cannot.
const GEM_PHASES = new Set(['Ruby', 'Sapphire', 'Black Pearl', 'Emerald'])

export default function PriceCard({ item, currency, rates }) {
  const rows = SOURCE_ORDER.map((key) => ({ key, ...(item.sources?.[key] || {}) }))

  let bestKey = null
  let bestVal = null
  for (const r of rows) {
    if (!r.online || r.price == null) continue
    const v = convert(r.price, r.currency, currency, rates)
    if (v == null) continue
    if (bestVal == null || v < bestVal) {
      bestVal = v
      bestKey = r.key
    }
  }

  const isKnife = item.category === 'knife'

  return (
    <article className="card">
      <div className="card-media">
        {item.image ? (
          <img src={item.image} alt={item.item_name} loading="lazy" />
        ) : (
          <div className="card-media-placeholder" aria-hidden="true">
            {item.item_name.replace('★ ', '').split('|')[0].trim()}
          </div>
        )}
        {item.phase && (
          <span className={`phase-badge ${GEM_PHASES.has(item.phase) ? 'gem' : ''}`}>
            {item.phase}
          </span>
        )}
      </div>

      <div className="card-head">
        <h3 title={item.item_name}>{item.item_name}</h3>
        <div className="tags">
          {item.wear && <span className="tag">{item.wear}</span>}
          {isKnife && <span className="tag tag-knife">Knife</span>}
          {item.stattrak && <span className="tag tag-st">StatTrak™</span>}
          {item.souvenir && <span className="tag tag-sv">Souvenir</span>}
        </div>
      </div>

      <table className="price-table">
        <tbody>
          {rows.map((r) => {
            const offline = !r.online || r.price == null
            const value = offline ? null : convert(r.price, r.currency, currency, rates)
            const phaseBlind = item.phase && r.key === 'csfloat' && !offline
            return (
              <tr
                key={r.key}
                className={[
                  offline ? 'offline' : '',
                  r.experimental ? 'experimental' : '',
                  r.key === bestKey ? 'best' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                <td className="src">
                  {r.url && !offline ? (
                    <a href={r.url} target="_blank" rel="noreferrer">
                      {SOURCE_LABELS[r.key]}
                    </a>
                  ) : (
                    SOURCE_LABELS[r.key]
                  )}
                  {r.experimental && <span className="mini-flag">exp</span>}
                  {phaseBlind && (
                    <span
                      className="mini-flag warn"
                      title="Name-based source can't distinguish Doppler phase"
                    >
                      no phase
                    </span>
                  )}
                </td>
                <td className="val">
                  {offline ? (
                    <span className="offline-label">offline</span>
                  ) : (
                    formatPrice(value, currency)
                  )}
                </td>
                <td className="age">{r.last_updated ? timeAgo(r.last_updated) : ''}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </article>
  )
}
