import { formatPrice } from '../lib/currency.js'
import { ALL_WEARS, buildMarketHashName } from '../lib/marketname.js'

// FN → BS quality color, like the in-game float bar.
const WEAR_COLORS = {
  'Factory New': '#35c46a',
  'Minimal Wear': '#9acd32',
  'Field-Tested': '#f5a623',
  'Well-Worn': '#e07b39',
  'Battle-Scarred': '#e5534b',
}

function cheapest(variants, convertFn) {
  let min = null
  for (const v of variants) {
    if (v.price_cny == null) continue
    const c = convertFn(v.price_cny)
    if (c == null) continue
    if (min == null || c < min) min = c
  }
  return min
}

export default function FinishList({
  finishes, openBase, setOpenBase, convertFn, currency, selected, onPick,
}) {
  return (
    <div className="finish-list">
      {finishes.map((f) => {
        const open = openBase === f.base
        const low = cheapest(f.variants || [], convertFn)

        // Which variant "types" to offer. Normal always; ST/Souvenir if Buff
        // showed them for this finish. Knives are never Souvenir.
        const types = [{ key: 'normal', label: 'Normal', st: false, sv: false }]
        if (f.stattrak_possible !== false && f.category !== 'souvenir') {
          types.push({ key: 'stattrak', label: 'StatTrak™', st: true, sv: false })
        }
        if (f.souvenir_possible) {
          types.push({ key: 'souvenir', label: 'Souvenir', st: false, sv: true })
        }

        // index the prices we already know from search, by name
        const known = {}
        for (const v of f.variants || []) known[v.market_hash_name] = v

        return (
          <div key={f.base} className={`finish ${open ? 'open' : ''}`}>
            <button
              type="button"
              className="finish-head"
              onClick={() => setOpenBase(open ? null : f.base)}
            >
              <span className="finish-name">
                {f.base}
                {f.category === 'knife' && <span className="tag tag-knife">Knife</span>}
              </span>
              <span className="finish-meta">
                {low != null
                  ? <>from <span className="from">{formatPrice(low, currency)}</span></>
                  : 'pick a condition'}
                <span className="chev">▼</span>
              </span>
            </button>

            {open && (
              <div className="variants">
                {types.map((t) => (
                  <div key={t.key} className="variant-group">
                    <span className={`group-label group-${t.key}`}>{t.label}</span>
                    <div className="chips">
                      {ALL_WEARS.map((wear) => {
                        const mhn = buildMarketHashName(f.base, wear, t.st, t.sv)
                        const hit = known[mhn]
                        const isSel = selected && selected.market_hash_name === mhn
                        const price =
                          hit && hit.price_cny != null ? convertFn(hit.price_cny) : null
                        return (
                          <button
                            key={wear}
                            type="button"
                            className={`chip ${isSel ? 'sel' : ''}`}
                            onClick={() =>
                              onPick(f.base, f.category, {
                                market_hash_name: mhn,
                                goods_id: hit ? hit.goods_id : null,
                                wear,
                                stattrak: t.st,
                                souvenir: t.sv,
                              })
                            }
                          >
                            <span className="chip-wear">
                              <span className="wear-dot" style={{ background: WEAR_COLORS[wear] }} />
                              {wear}
                            </span>
                            <span className={`chip-price ${price != null ? '' : 'unknown'}`}>
                              {price != null ? formatPrice(price, currency) : 'check →'}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
