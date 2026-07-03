// Build a Steam/Buff market_hash_name from parts, mirroring the Python rules.
// Phase is intentionally NOT encoded (it isn't part of the name).
export const ALL_WEARS = [
  'Factory New',
  'Minimal Wear',
  'Field-Tested',
  'Well-Worn',
  'Battle-Scarred',
]

export function buildMarketHashName(base, wear, stattrak, souvenir) {
  let core
  if (base.startsWith('★ ')) {
    const rest = base.slice(2)
    core = '★ ' + (stattrak ? 'StatTrak™ ' : '') + rest
  } else {
    const prefix = stattrak ? 'StatTrak™ ' : souvenir ? 'Souvenir ' : ''
    core = prefix + base
  }
  return wear ? `${core} (${wear})` : core
}
