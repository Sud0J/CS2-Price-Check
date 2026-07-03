// Client-side filtering helpers. Everything runs on the single prices.json.

export const WEARS = [
  'Factory New',
  'Minimal Wear',
  'Field-Tested',
  'Well-Worn',
  'Battle-Scarred',
]

export const PHASES = [
  'Phase 1',
  'Phase 2',
  'Phase 3',
  'Phase 4',
  'Ruby',
  'Sapphire',
  'Black Pearl',
  'Emerald',
]

// Rough weapon-type inference from the item name (strip star, before the "|").
export function weaponOf(itemName) {
  return (itemName || '').replace('★ ', '').split('|')[0].trim()
}

export function weaponTypes(items) {
  return Array.from(new Set(items.map((i) => weaponOf(i.item_name)))).sort()
}

// Lowest online price of an item, converted to display currency.
export function lowestConverted(item, convertFn) {
  let min = null
  for (const src of Object.values(item.sources || {})) {
    if (!src.online || src.price == null) continue
    const v = convertFn(src.price, src.currency)
    if (v == null) continue
    if (min == null || v < min) min = v
  }
  return min
}

export function applyFilters(items, f, convertFn) {
  const q = (f.query || '').toLowerCase().trim()
  return items.filter((item) => {
    if (q && !item.item_name.toLowerCase().includes(q)) return false
    if (f.weapon && weaponOf(item.item_name) !== f.weapon) return false
    if (f.wear && item.wear !== f.wear) return false
    if (f.phase && item.phase !== f.phase) return false
    if (f.category && item.category !== f.category) return false
    if (f.variant === 'stattrak' && !item.stattrak) return false
    if (f.variant === 'souvenir' && !item.souvenir) return false
    if (f.variant === 'normal' && (item.stattrak || item.souvenir)) return false

    const low = lowestConverted(item, convertFn)
    if (f.min != null && (low == null || low < f.min)) return false
    if (f.max != null && (low == null || low > f.max)) return false
    return true
  })
}
