// Client-side currency conversion.
//
// Rules (per requirement):
//   - USDT is pegged 1:1 to USD for cross-market comparison.
//   - VND is derived STRICTLY from the Binance P2P USDT sell price
//     (rates.usdt_vnd), i.e. price -> USD -> USDT(1:1) -> VND. We never use a
//     generic fiat VND rate.
//   - EUR / CNY use standard fiat cross rates.

export const CURRENCIES = ['USDT', 'USD', 'VND', 'CNY', 'EUR']

const SYMBOLS = { USDT: '₮', USD: '$', VND: '₫', CNY: '¥', EUR: '€' }

// amount in `from` currency -> USD.
// VND is ALWAYS the inverse of the Binance P2P USDT sell price (never the
// official fiat rate): VND -> USDT(=USD) = amount / usdt_vnd.
function toUsd(amount, from, rates, usdtVnd) {
  if (from === 'USD' || from === 'USDT') return amount
  if (from === 'VND') return usdtVnd ? amount / usdtVnd : null
  const r = rates?.[from]
  if (!r) return null
  return amount / r
}

// Convert `amount` (in `fromCurrency`) into `target`. `data` = /api/rates JSON.
export function convert(amount, fromCurrency, target, data) {
  if (amount == null || fromCurrency == null || !data) return null
  const rates = data.rates || {}
  const usd = toUsd(amount, fromCurrency, rates, data.usdt_vnd)
  if (usd == null) return null

  switch (target) {
    case 'USD':
    case 'USDT':
      return usd // 1 USDT ≈ 1 USD
    case 'EUR':
      return rates.EUR ? usd * rates.EUR : null
    case 'CNY':
      return rates.CNY ? usd * rates.CNY : null
    case 'VND':
      // strictly via Binance P2P USDT sell price
      return data.usdt_vnd ? usd * data.usdt_vnd : null
    default:
      return null
  }
}


// Convert a USD anchor (already in a source's own USD) into the target currency.
// Used for Buff (its own rate) and CSFloat (native USD). VND/USDT stay on
// Binance P2P; CNY/EUR use official fiat cross rates.
export function convertFromUsd(usd, target, data) {
  if (usd == null || !data) return null
  const rates = data.rates || {}
  switch (target) {
    case 'USD':
    case 'USDT':
      return usd
    case 'EUR':
      return rates.EUR ? usd * rates.EUR : null
    case 'CNY':
      return rates.CNY ? usd * rates.CNY : null
    case 'VND':
      return data.usdt_vnd ? usd * data.usdt_vnd : null
    default:
      return null
  }
}

export function formatPrice(amount, currency) {
  if (amount == null) return '—'
  const symbol = SYMBOLS[currency] || ''
  const noDecimals = currency === 'VND' || currency === 'CNY'
  const fixed = noDecimals
    ? Math.round(amount).toLocaleString('en-US')
    : amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return currency === 'VND' ? `${fixed}${symbol}` : `${symbol}${fixed}`
}

export function timeAgo(iso) {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'unknown'
  const mins = Math.floor((Date.now() - then) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}
