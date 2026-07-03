import { WEARS, PHASES } from '../lib/filters.js'

export default function Filters({ filters, setFilters, weapons }) {
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }))
  const num = (v) => (v === '' ? null : Number(v))

  return (
    <div className="filters">
      <select
        value={filters.category || ''}
        onChange={(e) => set({ category: e.target.value || null })}
      >
        <option value="">All types</option>
        <option value="gun">Guns</option>
        <option value="knife">Knives</option>
      </select>

      <select
        value={filters.weapon || ''}
        onChange={(e) => set({ weapon: e.target.value || null })}
      >
        <option value="">All items</option>
        {weapons.map((w) => (
          <option key={w} value={w}>
            {w}
          </option>
        ))}
      </select>

      <select
        value={filters.wear || ''}
        onChange={(e) => set({ wear: e.target.value || null })}
      >
        <option value="">All wears</option>
        {WEARS.map((w) => (
          <option key={w} value={w}>
            {w}
          </option>
        ))}
      </select>

      <select
        value={filters.phase || ''}
        onChange={(e) => set({ phase: e.target.value || null })}
      >
        <option value="">All phases</option>
        {PHASES.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>

      <select
        value={filters.variant || ''}
        onChange={(e) => set({ variant: e.target.value || null })}
      >
        <option value="">Any variant</option>
        <option value="normal">Normal</option>
        <option value="stattrak">StatTrak™</option>
        <option value="souvenir">Souvenir</option>
      </select>

      <div className="range">
        <input
          type="number"
          inputMode="decimal"
          placeholder="min"
          value={filters.min ?? ''}
          onChange={(e) => set({ min: num(e.target.value) })}
        />
        <span>–</span>
        <input
          type="number"
          inputMode="decimal"
          placeholder="max"
          value={filters.max ?? ''}
          onChange={(e) => set({ max: num(e.target.value) })}
        />
      </div>

      <button
        type="button"
        className="clear"
        onClick={() =>
          setFilters({
            query: filters.query,
            category: null,
            weapon: null,
            wear: null,
            phase: null,
            variant: null,
            min: null,
            max: null,
          })
        }
      >
        Reset
      </button>
    </div>
  )
}
