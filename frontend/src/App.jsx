import { useEffect, useState } from 'react'

function App() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(setHealth)
      .catch((err) => setError(err.message))
  }, [])

  return (
    <main>
      <h1>LoL Draft Recommender</h1>
      <h2>Backend status</h2>
      {error && <p className="error">Backend unreachable: {error}</p>}
      {!error && !health && <p>Checking backend…</p>}
      {health && (
        <ul>
          <li>
            API: <span className="ok">{health.status}</span>
          </li>
          <li>
            Database: <span className={health.database === 'ok' ? 'ok' : 'error'}>{health.database}</span>
            {' '}(schema v{health.schema_version})
          </li>
          <li>
            Riot API key:{' '}
            {health.riot_api_key_configured
              ? <span className="ok">configured</span>
              : <span className="error">missing – add it to .env</span>}
          </li>
        </ul>
      )}
    </main>
  )
}

export default App
