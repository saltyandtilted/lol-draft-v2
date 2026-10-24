import { POSITION_LABELS, POSITIONS } from '../labels.js'
import ChampionPicker from './ChampionPicker.jsx'

const MAX_BANS = 10

function usedIds(draft) {
  return new Set([...Object.values(draft.allies), ...Object.values(draft.enemies), ...draft.bans].filter(Boolean))
}

export default function DraftForm({ champions, platforms, draft, onChange, onSubmit, loading }) {
  const used = usedIds(draft)
  const set = (patch) => onChange({ ...draft, ...patch })

  const setPosition = (position) => {
    // Nobody else on my team can play my role.
    const allies = { ...draft.allies }
    delete allies[position]
    set({ position, allies })
  }

  return (
    <form
      className="draft"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }}
    >
      <fieldset className="player">
        <legend>You</legend>
        <label>
          <span>Riot ID <small className="muted">(optional – adds your form and mastery)</small></span>
          <input
            type="text"
            placeholder="Name#TAG"
            value={draft.riotId}
            onChange={(e) => set({ riotId: e.target.value })}
          />
        </label>
        <label>
          Region
          <select value={draft.platform} onChange={(e) => set({ platform: e.target.value })}>
            {platforms.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </label>
        <div className="roles" role="radiogroup" aria-label="Your role">
          {POSITIONS.map((p) => (
            <button
              key={p}
              type="button"
              role="radio"
              aria-checked={draft.position === p}
              className={draft.position === p ? 'role active' : 'role'}
              onClick={() => setPosition(p)}
            >
              {POSITION_LABELS[p]}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="teams">
        <fieldset>
          <legend>Allies</legend>
          {POSITIONS.filter((p) => p !== draft.position).map((p) => (
            <label key={p} className="slot">
              <span>{POSITION_LABELS[p]}</span>
              <ChampionPicker
                champions={champions}
                value={draft.allies[p] ?? null}
                onChange={(id) => set({ allies: { ...draft.allies, [p]: id } })}
                disabled={used}
                role={p}
                placeholder="not picked yet"
              />
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>Enemies</legend>
          {POSITIONS.map((p) => (
            <label key={p} className="slot">
              <span>{POSITION_LABELS[p]}</span>
              <ChampionPicker
                champions={champions}
                value={draft.enemies[p] ?? null}
                onChange={(id) => set({ enemies: { ...draft.enemies, [p]: id } })}
                disabled={used}
                role={p}
                placeholder="unknown"
              />
            </label>
          ))}
        </fieldset>
      </div>

      <fieldset>
        <legend>Bans ({draft.bans.length}/{MAX_BANS})</legend>
        <div className="bans">
          {draft.bans.map((id) => {
            const c = champions.find((x) => x.id === id)
            return (
              <button
                key={id}
                type="button"
                className="ban"
                title={`Remove ban: ${c?.name}`}
                onClick={() => set({ bans: draft.bans.filter((b) => b !== id) })}
              >
                <img src={c?.icon} alt={c?.name} width="32" height="32" />
              </button>
            )
          })}
          {draft.bans.length < MAX_BANS && (
            <ChampionPicker
              champions={champions}
              value={null}
              onChange={(id) => id && set({ bans: [...draft.bans, id] })}
              disabled={used}
              placeholder="add ban"
            />
          )}
        </div>
      </fieldset>

      <div className="actions">
        <button type="submit" className="primary" disabled={loading}>
          {loading ? (draft.riotId.trim() ? 'Loading your profile…' : 'Computing…') : 'Recommend'}
        </button>
        <button
          type="button"
          onClick={() => set({ allies: {}, enemies: {}, bans: [] })}
          disabled={loading}
        >
          Clear draft
        </button>
      </div>
    </form>
  )
}
