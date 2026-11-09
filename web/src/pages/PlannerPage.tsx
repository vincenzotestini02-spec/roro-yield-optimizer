import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, pollJob } from '../api'
import type { PlannerStateBody } from '../api'
import { DeckView } from '../components/DeckView'
import { StabilityView } from '../components/StabilityView'
import { euro } from '../format'
import { loadPlanner, savePlanner } from '../planner'
import type { Demand, LabDefaults, PlannerBookingIn, PlannerPlan, PlannerSession, PlannerVessel, RowError } from '../types'

const DEFAULT_DEMAND: Demand = { level: 'normal', contract_share: 0.45, spot_rate_multiplier: 1, window_days: 14, hours_to_departure: 72 }
const PLANNER_LOST_SPACE = 0.15
const VESSEL_KEYS = ['n_lanes', 'lane_length_m', 'max_dwt_t', 'reefer_plugs', 'lashing_gap_m', 'max_heel_deg', 'max_trim_m',
  'ballast_tank_cap_t', 'ballast_cost_per_t', 'broken_stowage_pct', 'displacement_t', 'gm_m', 'mtc_tm_per_cm']

function message(e: unknown): string {
  return e instanceof ApiError ? e.detail : 'Something went wrong.'
}

function vesselFor(defaults: LabDefaults, preset: string, lostSpace: number): PlannerVessel {
  const merged: Record<string, number> = { ...defaults.values, ...defaults.presets[preset].values }
  const vessel: PlannerVessel = { preset }
  for (const key of VESSEL_KEYS) if (key in merged) vessel[key] = merged[key]
  vessel.broken_stowage_pct = lostSpace
  return vessel
}

export function emptySession(vessel: PlannerVessel): PlannerSession {
  return { vessel, bookings: [], placements: {}, demand: DEFAULT_DEMAND, log: [] }
}

export function stateOf(session: PlannerSession): PlannerStateBody {
  return { vessel: session.vessel, bookings: session.bookings, placements: session.placements }
}

export function PlannerPage() {
  const [loaded] = useState(() => loadPlanner())
  const [defaults, setDefaults] = useState<LabDefaults | null>(null)
  const [session, setSession] = useState<PlannerSession | null>(loaded.session)
  const [plan, setPlan] = useState<PlannerPlan | null>(null)
  const [rowErrors, setRowErrors] = useState<RowError[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const latest = useRef(0)

  const store = useCallback((next: PlannerSession) => {
    setSession(next)
    savePlanner(next)
  }, [])

  const replan = useCallback(async (next: PlannerSession) => {
    store(next)
    if (next.bookings.length === 0) { setPlan(null); return }
    const request = ++latest.current  // only the newest plan may change the page
    setBusy(true)
    setError(null)
    try {
      const { job_id } = await api.plannerPlan(stateOf(next))
      const result = await pollJob<PlannerPlan>(job_id, () => {})
      if (request !== latest.current) return
      setPlan(result)
      store({ ...next, placements: result.placements })
    } catch (e) {
      if (request === latest.current) setError(message(e))
    } finally {
      if (request === latest.current) setBusy(false)
    }
  }, [store])

  useEffect(() => {
    api.labDefaults().then((d) => {
      setDefaults(d)
      if (loaded.session === null) store(emptySession(vesselFor(d, 'demo', PLANNER_LOST_SPACE)))
      else void replan(loaded.session)
    }).catch((e) => setError(message(e)))
  }, [loaded, replan, store])

  async function upload(file: File | undefined) {
    if (file === undefined || session === null) return
    setRowErrors([])
    setWarnings([])
    setError(null)
    try {
      const result = await api.importBookings(file)
      setWarnings(result.warnings)
      if (result.errors.length > 0) { setRowErrors(result.errors); return }
      setPlan(null)
      await replan({ ...session, bookings: result.bookings, placements: {}, log: [] })
    } catch (e) {
      setError(message(e))
    }
  }

  function changeVessel(preset: string) {
    if (defaults === null || session === null) return
    void replan({ ...session, vessel: vesselFor(defaults, preset, Number(session.vessel.broken_stowage_pct)) })
  }

  function changeLostSpace(value: number) {
    if (session === null) return
    void replan({ ...session, vessel: { ...session.vessel, broken_stowage_pct: value } })
  }

  const byId = new Map((session?.bookings ?? []).map((b): [string, PlannerBookingIn] => [b.booking_id, b]))

  return (
    <>
      <div className="stack">
        <h1>Planner</h1>
        <p className="muted">Upload the accepted bookings, get a deck plan, then judge new requests as they come in.</p>
        <p className="notice">Planning estimate, not a loading computer.</p>
      </div>
      {loaded.damaged && <p className="notice">Your saved planner session could not be read and was cleared.</p>}
      {error && <p className="notice">{error}</p>}
      <div className="grid-2">
        <section className="card" aria-label="Planner settings">
          {defaults && session && (
            <>
              <label className="field">
                <span>Vessel</span>
                <select aria-label="Vessel" value={String(session.vessel.preset)} onChange={(e) => changeVessel(e.target.value)}>
                  {Object.entries(defaults.presets).map(([key, p]) => <option key={key} value={key}>{p.label}</option>)}
                </select>
                <span className="small muted">{defaults.note}</span>
              </label>
              <label className="field">
                <span>Lost space (broken stowage)<strong>{Math.round(Number(session.vessel.broken_stowage_pct) * 100)}%</strong></span>
                <input type="range" min={0} max={0.3} step={0.01} value={Number(session.vessel.broken_stowage_pct)}
                  onChange={(e) => changeLostSpace(Number(e.target.value))} />
              </label>
            </>
          )}
          <a href="/api/planner/template.xlsx" download>Download template</a>
          <label className="field">
            <span>Upload bookings (.xlsx)</span>
            <input type="file" accept=".xlsx" aria-label="Upload bookings" onChange={(e) => void upload(e.target.files?.[0])} />
          </label>
          {warnings.map((w) => <p key={w} className="notice small">{w}</p>)}
        </section>
        <div className="stack">
          {rowErrors.length > 0 && (
            <section className="card">
              <h2>The file has errors</h2>
              <p className="small muted">Nothing was imported. Fix these rows and upload again.</p>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Row</th><th>Column</th><th>Problem</th></tr></thead>
                  <tbody>{rowErrors.map((e, i) => <tr key={i}><td>{e.row}</td><td>{e.column}</td><td className="wrap">{e.message}</td></tr>)}</tbody>
                </table>
              </div>
            </section>
          )}
          {busy && <p className="muted">Planning…</p>}
          {plan && (
            <>
              <div className="grid-3">
                <div className="card"><span className="small muted">Units loaded</span><span className="value">{plan.kpis.n_accepted} of {session?.bookings.length}</span></div>
                <div className="card"><span className="small muted">Revenue</span><span className="value" data-testid="revenue">{plan.revenue_known ? euro(plan.kpis.revenue) : 'n/a'}</span></div>
                <div className="card"><span className="small muted">Deck used</span><span className="value">{plan.deck.used_m.toFixed(0)} / {plan.deck.usable_m.toFixed(0)} m</span></div>
              </div>
              <section className="card">
                <DeckView deck={plan.deck} />
                <StabilityView deck={plan.deck} />
              </section>
              {plan.excluded.length > 0 && (
                <section className="card">
                  <h2>Excluded</h2>
                  <p>Accepted bookings are never dropped silently: decide how to handle these.</p>
                  <ul>
                    {plan.excluded.map((e) => {
                      const b = byId.get(e.booking_id)
                      return <li key={e.booking_id}><strong>{e.booking_id}</strong>{b ? ` · ${b.customer} · ${b.length_m} m` : ''}: {e.reason}</li>
                    })}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}
