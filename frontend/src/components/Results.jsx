import { GOAL_LABELS } from '../labels.js'
import RecommendationCard from './RecommendationCard.jsx'

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '–'
}

export default function Results({ result }) {
  const { candidates, meta, profile, warnings } = result
  const rho = meta.spearman || {}

  return (
    <section className="results">
      <h2>{candidates.length ? `Top ${candidates.length} for ${meta.position}` : 'No recommendation'}</h2>
      {profile.used && (
        <p className="muted">
          Profile: {profile.games} recent ranked games, mastery on {profile.mastery_champions} champions
          {profile.cached ? ' (cached)' : ''}.
        </p>
      )}
      {warnings.map((w) => (
        <p key={w} className="warning">{w}</p>
      ))}

      <div className="cards">
        {candidates.map((c) => (
          <RecommendationCard key={c.champion_id} candidate={c} />
        ))}
      </div>

      <dl className="meta">
        <div><dt>Patch</dt><dd>{meta.patch}</dd></div>
        <div><dt>Data from</dt><dd>{formatDate(meta.data_computed_at)}</dd></div>
        <div><dt>Matches</dt><dd>{meta.matches_used}</dd></div>
        <div><dt>Candidates</dt><dd>{meta.candidates}</dd></div>
        <div><dt>Known enemies</dt><dd>{meta.known_enemies}/5</dd></div>
        <div><dt>AHP CR</dt><dd>{meta.ahp_cr}</dd></div>
        <div>
          <dt>Spearman ρ vs TOPSIS</dt>
          <dd>PROMETHEE {rho.promethee_ii ?? '–'} · VIKOR {rho.vikor ?? '–'}</dd>
        </div>
        {meta.dropped_criteria?.length > 0 && (
          <div>
            <dt>Dropped (same for all)</dt>
            <dd>{meta.dropped_criteria.map((g) => GOAL_LABELS[g] ?? g).join(', ')}</dd>
          </div>
        )}
      </dl>
    </section>
  )
}
