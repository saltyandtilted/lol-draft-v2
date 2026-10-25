import { GOAL_LABELS } from '../labels.js'

const WIN_PARTS = [
  ['A', 'Champion strength'],
  ['B', 'Matchups'],
  ['C', 'Synergy'],
  ['D', 'Your form'],
]

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

export default function RecommendationCard({ candidate: c }) {
  // JSON keys arrive sorted alphabetically; show the goals in model order (W, E, F).
  const contributions = Object.keys(GOAL_LABELS)
    .filter((goal) => goal in c.contributions)
    .map((goal) => [goal, c.contributions[goal]])
  const totalContribution = contributions.reduce((sum, [, value]) => sum + value, 0)

  return (
    <article className="card">
      <header>
        <span className="rank">#{c.rank}</span>
        <img src={c.icon} alt="" width="56" height="56" />
        <div className="title">
          <h3>{c.name}</h3>
          <span className="muted">score {c.score.toFixed(3)}</span>
        </div>
        <div className="win" title="Estimated win chance from criteria A–D">
          <strong>{(c.win_estimate * 100).toFixed(1)} %</strong>
          <span className="muted">est. win</span>
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

      <table className="breakdown">
        <tbody>
          {WIN_PARTS.map(([key, label]) => (
            <tr key={key}>
              <th>{label}</th>
              <td className={tone(c.criteria_pp[key])}>
                {signed(c.criteria_pp[key])} pp
              </td>
              <td>{c.low_data[key] && <span className="badge" title="Few games: value shrunk towards neutral">low data</span>}</td>
            </tr>
          ))}
          <tr>
            <th>Comfort (mastery)</th>
            <td>{percent(c.criteria.E)}</td>
            <td />
          </tr>
          <tr>
            <th>Team balance</th>
            <td className={tone(c.criteria.F, 3)}>{signed(c.criteria.F, 3)}</td>
            <td />
          </tr>
        </tbody>
      </table>

      <footer className="muted">
        <span title="Ranked games on this champion in this role">{c.games} games</span>
        <span title="Width of the 95 % interval of the champion's win rate">interval ±{(c.interval_pp / 2).toFixed(1)} pp</span>
        <span title="Share of weight simulations (SMAA) in which the champion stays in the top 5">
          top-5 stability {percent(c.top5_probability)}
        </span>
        <span title="Rank by the control methods">PROMETHEE #{c.promethee_rank} · VIKOR #{c.vikor_rank}</span>
      </footer>
    </article>
  )
}
