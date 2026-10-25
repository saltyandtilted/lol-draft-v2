import { GOAL_LABELS } from '../labels.js'

// Log-odds criteria shown as percentage points; the meter is full at this many points.
const WIN_PARTS = [
  ['A', 'Champion strength'],
  ['B', 'Matchups'],
  ['C', 'Synergy'],
  ['D', 'Your form'],
]
const PP_SCALE = 3
const BALANCE_SCALE = 0.3

function signed(value, digits = 1) {
  const text = value.toFixed(digits)
  return value > 0 ? `+${text}` : text
}

// Colour only values that are not zero after rounding ("+0.0 pp" in green looked like a gain).
function tone(value, digits = 1) {
  const shown = Number(value.toFixed(digits))
  return shown > 0 ? 'pos' : shown < 0 ? 'neg' : ''
}

function percent(value) {
  return `${Math.round(value * 100)} %`
}

// Data Dragon serves the centred splash art next to the square icon: .../champion/<Key>.png.
function splashUrl(icon) {
  const key = icon?.match(/\/champion\/([^/]+)\.png$/)?.[1]
  return key ? `https://ddragon.leagueoflegends.com/cdn/img/champion/centered/${key}_0.jpg` : null
}

// Bar growing right (gain) or left (loss) from the centre line.
function Meter({ value, scale, digits }) {
  const width = Math.min(Math.abs(value) / scale, 1) * 50
  const cls = tone(value, digits)
  return (
    <span className="meter">
      {cls && <i className={cls} style={{ width: `${width}%`, left: value > 0 ? '50%' : `${50 - width}%` }} />}
    </span>
  )
}

export default function RecommendationCard({ candidate: c }) {
  // JSON keys arrive sorted alphabetically; show the goals in model order (W, E, F).
  const contributions = Object.keys(GOAL_LABELS)
    .filter((goal) => goal in c.contributions)
    .map((goal) => [goal, c.contributions[goal]])
  const totalContribution = contributions.reduce((sum, [, value]) => sum + value, 0)
  const splash = splashUrl(c.icon)

  return (
    <article className="card" style={splash ? { '--splash': `url(${splash})` } : undefined}>
      <header>
        <span className="rank">{c.rank}</span>
        <img src={c.icon} alt="" width="60" height="60" />
        <div className="title">
          <h3>{c.name}</h3>
          <span className="muted">score {c.score.toFixed(3)}</span>
        </div>
        <div className="win" title="Estimated win chance from criteria A–D">
          <strong>{(c.win_estimate * 100).toFixed(1)}<small>%</small></strong>
          <span>est. win</span>
        </div>
      </header>

      <ul className="why">
        {c.why.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>

      <div className="bar" aria-label="Score contributions">
        {contributions.map(([goal, value]) => (
          <span
            key={goal}
            className={`seg seg-${goal}`}
            style={{ width: `${(value / Math.max(totalContribution, 1e-9)) * 100}%` }}
            title={`${GOAL_LABELS[goal]}: ${value.toFixed(3)}`}
          />
        ))}
      </div>
      <div className="legend">
        {contributions.map(([goal, value]) => (
          <span key={goal}>
            <i className={`dot seg-${goal}`} /> {GOAL_LABELS[goal]} {value.toFixed(2)}
          </span>
        ))}
      </div>

      <div className="criteria">
        {WIN_PARTS.map(([key, label]) => (
          <div key={key} className="criterion">
            <span className="label">
              {label}
              {c.low_data[key] && <span className="badge" title="Few games: value shrunk towards neutral">low data</span>}
            </span>
            <Meter value={c.criteria_pp[key]} scale={PP_SCALE} digits={1} />
            <span className={`value ${tone(c.criteria_pp[key])}`}>{signed(c.criteria_pp[key])} pp</span>
          </div>
        ))}
        <div className="criterion">
          <span className="label">Comfort (mastery)</span>
          <span className="meter plain">
            <i className="comfort" style={{ width: `${c.criteria.E * 100}%` }} />
          </span>
          <span className="value">{percent(c.criteria.E)}</span>
        </div>
        <div className="criterion">
          <span className="label">Team balance</span>
          <Meter value={c.criteria.F} scale={BALANCE_SCALE} digits={3} />
          <span className={`value ${tone(c.criteria.F, 3)}`}>{signed(c.criteria.F, 3)}</span>
        </div>
      </div>

      <footer>
        <span
          className="ring"
          style={{ '--p': c.top5_probability * 100 }}
          title="Share of weight simulations (SMAA) in which the champion stays in the top 5"
        >
          <b>{Math.round(c.top5_probability * 100)}</b>
        </span>
        <span className="stat"><em>top-5 stability</em></span>
        <span className="stat" title="Ranked games on this champion in this role"><b>{c.games}</b> games</span>
        <span className="stat" title="Width of the 95 % interval of the champion's win rate">
          <b>±{(c.interval_pp / 2).toFixed(1)}</b> pp interval
        </span>
        <span className="stat" title="Rank by the control methods">
          PROMETHEE <b>#{c.promethee_rank}</b> · VIKOR <b>#{c.vikor_rank}</b>
        </span>
      </footer>
    </article>
  )
}
