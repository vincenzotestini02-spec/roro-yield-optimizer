import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, pollJob } from '../api'
import { DeckView } from '../components/DeckView'
import { JobProgress } from '../components/JobProgress'
import { StabilityView } from '../components/StabilityView'
import { euro, pctAgainst } from '../format'
import { clearGame, loadGame } from '../storage'
import type { BestResult, Booking, PlanResult, RevealResult, SavedGame } from '../types'

function PlanCard({ plan, fcfs }: { plan: PlanResult; fcfs: PlanResult }) {
  const k = plan.kpis
  const delta = plan === fcfs ? null : pctAgainst(k.objective, fcfs.kpis.objective)
  return (
    <div className="card">
      <span className="small muted">{plan.method}</span>
      <span className="value">{euro(k.objective)}</span>
      {delta && <span className={`small ${delta.startsWith('+') ? 'good' : 'bad'}`}>{delta} vs FCFS</span>}
      <span className="small muted">
        RevPAL €{k.revpal.toFixed(1)}/lm · deck {k.deck_util_pct.toFixed(0)}% · DWT {k.dwt_pct.toFixed(0)}% · {k.n_accepted} units
        {k.shortfall_m > 0 ? ` · shortfall ${k.shortfall_m.toFixed(0)} m (−€${k.penalty.toFixed(0)})` : ''}
        {` · ballast ${k.ballast_t.toFixed(0)} t · heel ${k.heel_deg.toFixed(1)}° · trim ${k.trim_m.toFixed(2)} m`}
      </span>
    </div>
  )
}

function Waiting({ label, note }: { label: string; note: string }) {
  return <div className="card"><span className="small muted">{label}</span><span className="muted">{note}</span></div>
}

function AdvisorTable({ game, requests }: { game: SavedGame; requests: Booking[] }) {
  const actions = new Map(game.decisions.map((d) => [d.booking_id, d.action]))
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>#</th><th>Request</th><th>You</th><th>Advisor</th><th>Futures</th><th className="num">Expected gain</th><th>✗</th></tr>
        </thead>
        <tbody>
          {requests.map((b, i) => {
            const you = actions.get(b.id)
            const v = game.verdicts[b.id]
            const advisor = v === undefined ? 'n/a' : `${v.accept ? 'accept' : 'reject'}${v.feasible ? '' : " (doesn't fit)"}`
            const disagrees = v !== undefined && v.accept !== (you === 'accept')
            return (
              <tr key={b.id}>
                <td>{i + 1}</td>
                <td>{`${b.id} ${b.unit_label}, ${b.segment}`}</td>
                <td>{you}</td>
                <td>{advisor}</td>
                <td>{v?.feasible ? `${v.n_pays_off}/${v.k}` : ''}</td>
                <td className="num">{v?.feasible ? euro(v.expected_gain_eur) : ''}</td>
                <td>{disagrees ? '✗' : ''}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function RevealPage() {
  const navigate = useNavigate()
  const [game] = useState<SavedGame | null>(() => loadGame())
  const [ready, setReady] = useState(game !== null)
  const [requests, setRequests] = useState<Booking[]>([])
  const [reveal, setReveal] = useState<RevealResult | null>(null)
  const [smart, setSmart] = useState<PlanResult | null>(null)
  const [smartFailed, setSmartFailed] = useState(false)
  const [progress, setProgress] = useState(0)
  const [best, setBest] = useState<BestResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [shown, setShown] = useState(0)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (game === null) return
    const abort = new AbortController()
    async function run(saved: SavedGame) {
      setError(null)
      const state = await api.gameState(saved.seed, saved.decisions)
      if (!state.finished) { setReady(false); return }
      setRequests(state.past)
      const first = await api.reveal(saved.seed, saved.decisions)
      setReveal(first)
      try {
        setSmart(await pollJob<PlanResult>(first.smart_job, setProgress, abort.signal))
      } catch (e) {
        if (abort.signal.aborted) return
        if (e instanceof ApiError && e.status === 404) throw e
        setSmartFailed(true)
      }
      const job = await api.bestPlan(saved.seed, saved.decisions, first.smart_job)
      setBest(await pollJob<BestResult>(job.job_id, () => {}, abort.signal))
    }
    run(game).catch((e) => {
      if (!abort.signal.aborted) setError(e instanceof ApiError ? e.detail : 'Something went wrong.')
    })
    return () => abort.abort()
  }, [game, attempt])

  if (game === null || !ready) {
    return <p>Nothing to reveal yet. <Link to="/">Play a sailing</Link></p>
  }

  const plans = reveal === null ? [] : [reveal.fcfs, reveal.you, ...(smart ? [smart] : []), ...(best ? [best.plan] : [])]
  const plan = plans[Math.min(shown, plans.length - 1)]

  return (
    <>
      <div className="stack">
        <h1>The ship has sailed. How did you do?</h1>
        <p className="muted">Score = margin − contract-shortfall penalty − ballast cost. Same rules and same requests for all four.</p>
      </div>
      {error && (
        <div className="notice stack">
          <p>{error}</p>
          <div><button onClick={() => setAttempt(attempt + 1)}>Try again</button></div>
        </div>
      )}
      {reveal && (
        <div className="grid-4">
          <PlanCard plan={reveal.fcfs} fcfs={reveal.fcfs} />
          <PlanCard plan={reveal.you} fcfs={reveal.fcfs} />
          {smart ? <PlanCard plan={smart} fcfs={reveal.fcfs} />
            : <Waiting label="Smart planner (no foresight)" note={smartFailed ? 'Unavailable for this sailing.' : 'Playing the sailing…'} />}
          {best ? <PlanCard plan={best.plan} fcfs={reveal.fcfs} /> : <Waiting label="Best possible" note="Waits for the smart planner." />}
        </div>
      )}
      {reveal && !smart && !smartFailed && <JobProgress label="The smart planner is playing this sailing" progress={progress} />}
      {plan && (
        <section className="card">
          <div className="row">
            {plans.map((p, i) => (
              <button key={p.method} aria-pressed={p === plan} className={p === plan ? 'primary' : ''} onClick={() => setShown(i)}>{p.method}</button>
            ))}
          </div>
          <DeckView deck={plan.deck} />
          <StabilityView deck={plan.deck} />
        </section>
      )}
      <section className="card">
        <h2>You vs the advisor, request by request</h2>
        <AdvisorTable game={game} requests={requests} />
        <p className="small muted">✗ = you and the advisor disagreed. n/a = the Advisor was off for that request. It knows only the demand distribution, never the requests still to come.</p>
      </section>
      {best && (
        <section className="card">
          <h2>Where you lost the most</h2>
          {best.costly.length === 0 ? <p className="good">You matched the best possible plan.</p> : (
            <ul>{best.costly.map((d, i) => <li key={i}>{d.booking_id ? <strong>{d.booking_id} · </strong> : null}{d.reason}</li>)}</ul>
          )}
        </section>
      )}
      <div className="row">
        <button onClick={() => { clearGame(); navigate('/') }}>Play another sailing</button>
        <button className="primary" onClick={() => navigate('/lab')}>Open the Lab</button>
      </div>
    </>
  )
}
