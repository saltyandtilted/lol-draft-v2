import { useMemo, useState } from 'react'

const MAX_OPTIONS = 40

// Searchable champion select with Data Dragon icons.
// `role` sorts champions viable in that role first; `disabled` is a Set of ids already used.
export default function ChampionPicker({ champions, value, onChange, disabled, role, placeholder }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const selected = champions.find((c) => c.id === value)

  const options = useMemo(() => {
    const q = query.trim().toLowerCase()
    const matches = champions.filter((c) => !disabled.has(c.id) && c.name.toLowerCase().includes(q))
    if (role) {
      matches.sort((a, b) => Number(b.positions.includes(role)) - Number(a.positions.includes(role)))
    }
    return matches.slice(0, MAX_OPTIONS)
  }, [champions, disabled, query, role])

  if (selected) {
    return (
      <div className="picker picked">
        <img src={selected.icon} alt="" width="28" height="28" />
        <span>{selected.name}</span>
        <button type="button" className="clear" onClick={() => onChange(null)} aria-label={`Remove ${selected.name}`}>
          ×
        </button>
      </div>
    )
  }

  const choose = (champion) => {
    onChange(champion.id)
    setQuery('')
    setOpen(false)
  }

  return (
    <div className="picker">
      <input
        type="text"
        value={query}
        placeholder={placeholder}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          // Leftover search text would look like a picked champion.
          setQuery('')
          setOpen(false)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && options.length) {
            e.preventDefault()
            choose(options[0])
          }
          if (e.key === 'Escape') setOpen(false)
        }}
      />
      {open && (
        <ul className="options" role="listbox">
          {options.length === 0 && <li className="empty">No champion found</li>}
          {options.map((c) => (
            // onMouseDown fires before the input's blur, so the click is not lost.
            <li key={c.id} role="option" onMouseDown={(e) => { e.preventDefault(); choose(c) }}>
              <img src={c.icon} alt="" width="24" height="24" loading="lazy" />
              <span>{c.name}</span>
              {role && !c.positions.includes(role) && <small>off-role</small>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
