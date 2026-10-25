import { useEffect, useState } from 'react'

import { api } from './api.js'
import DraftForm from './components/DraftForm.jsx'
import Results from './components/Results.jsx'

const SAVED_PLAYER = 'lol-draft.player'

function initialDraft() {
  let saved = {}
  try {
    saved = JSON.parse(localStorage.getItem(SAVED_PLAYER)) || {}
  } catch {
    // Storage blocked or corrupted: start empty.
  }
  return {
    riotId: saved.riotId ?? '',
    platform: saved.platform ?? 'eun1',
    position: saved.position ?? 'TOP',
    allies: {},
    enemies: {},
    bans: [],
  }
}

function toRequest(draft) {
  const picks = (team) =>
    Object.entries(team)
      .filter(([, id]) => id)
      .map(([position, champion_id]) => ({ champion_id, position }))
  return {
    riot_id: draft.riotId.trim() || null,
    platform: draft.platform,
    position: draft.position,
    allies: picks(draft.allies),
    enemies: picks(draft.enemies),
    bans: draft.bans,
  }
}

function App() {
  const [health, setHealth] = useState(null)
  const [meta, setMeta] = useState(null)
  const [champions, setChampions] = useState([])
  const [startupError, setStartupError] = useState(null)
  const [draft, setDraft] = useState(initialDraft)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api('/health').then(setHealth).catch(() => {})
    Promise.all([api('/meta'), api('/champions')])
      .then(([m, c]) => {
        setMeta(m)
        setChampions(c.champions)
      })
      .catch((err) => setStartupError(err.message))
  }, [])

  useEffect(() => {
    const { riotId, platform, position } = draft
    try {
      localStorage.setItem(SAVED_PLAYER, JSON.stringify({ riotId, platform, position }))
    } catch {
      // Remembering the player is only a convenience.
    }
  }, [draft])

  const submit = async () => {
    setLoading(true)
    setError(null)
    try {
      setResult(await api('/recommend', { method: 'POST', body: toRequest(draft) }))
    } catch (err) {
      setResult(null)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <header className="top">
        <h1>LoL Draft Recommender</h1>
        <p className="muted status">
          {meta ? `Patch ${meta.patch} · ${meta.matches_used} matches` : ''}
          {health && !health.riot_api_key_configured && (
            <span className="error"> · Riot API key missing in .env (Riot ID lookup disabled)</span>
          )}
        </p>
      </header>
      <div className="ornament" aria-hidden="true" />

      {startupError && <p className="error banner">{startupError}</p>}
      {!startupError && !meta && <p className="muted">Loading champions…</p>}

      {meta && (
        <div className="layout">
          <DraftForm
            champions={champions}
            platforms={meta.platforms}
            draft={draft}
            onChange={setDraft}
            onSubmit={submit}
            loading={loading}
          />
          <div className="output">
            {error && <p className="error banner">{error}</p>}
            {result ? (
              <Results result={result} />
            ) : (
              !error && (
                <div className="empty-state">
                  <p className="empty-title">Your top 5 picks will appear here</p>
                  <p className="muted">
                    Choose your role, add the champions you already know and press Recommend.
                    Every field is optional.
                  </p>
                </div>
              )
            )}
          </div>
        </div>
      )}
    </main>
  )
}

export default App
