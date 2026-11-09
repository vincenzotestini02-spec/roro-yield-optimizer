import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, pollJob } from '../api'
import type { PlannerStateBody } from '../api'
import { DeckView } from '../components/DeckView'
import { RequestPanel } from '../components/RequestPanel'
import { StabilityView } from '../components/StabilityView'
import { downloadBlob } from '../download'
import { euro } from '../format'
import { clearPlanner, loadPlanner, parseSessionFile, savePlanner } from '../planner'
import type { Demand, LabDefaults, PlannerBookingIn, PlannerPlan, PlannerSession, PlannerVerdict, PlannerVessel, RowError } from '../types'

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
  const [selected, setSelected] = useState<string | null>(null)
  const [moved, setMoved] = useState<string[]>([])
  const [verdict, setVerdict] = useState<PlannerVerdict | null>(null)
  const [asking, setAsking] = useState(false)
  const latest = useRef(0)
  const runningJob = useRef<string | null>(null)
  const lostSpaceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const store = useCallback((next: PlannerSession) => {
    setSession(next)
    savePlanner(next)
  }, [])

  const replan = useCallback(async (next: PlannerSession) => {
    store(next)
    if (next.bookings.length === 0) { setPlan(null); return }
    const request = ++latest.current  // only the newest plan may change the page
    if (runningJob.current !== null) void api.cancelJob?.(runningJob.current)?.catch(() => {})
    runningJob.current = null
    setBusy(true)
    setError(null)
    try {
      const { job_id } = await api.plannerPlan(stateOf(next))
      if (request === latest.current) runningJob.current = job_id
      const result = await pollJob<PlannerPlan>(job_id, () => {})
      if (request !== latest.current) return
      setPlan(result)
      setMoved(result.moved)
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
    // Show the value at once, but plan only once the slider has settled.
    const next = { ...session, vessel: { ...session.vessel, broken_stowage_pct: value } }
    store(next)
    if (lostSpaceTimer.current !== null) clearTimeout(lostSpaceTimer.current)
    lostSpaceTimer.current = setTimeout(() => void replan(next), 600)
  }

  function startOver() {
    if (defaults === null) return
    clearPlanner()
    latest.current += 1
    setPlan(null)
    setError(null)
    setBusy(false)
    store(emptySession(vesselFor(defaults, 'demo', PLANNER_LOST_SPACE)))
  }

  function changeDemand(demand: Demand) {
    if (session === null) return
    store({ ...session, demand })
  }

  async function ask(request: PlannerBookingIn) {
    if (session === null) return
    setAsking(true)
    setError(null)
    setVerdict(null)
    try {
      const { job_id } = await api.plannerAdvise(stateOf(session), request, session.demand)
      setVerdict(await pollJob<PlannerVerdict>(job_id, () => {}))
    } catch (e) {
      setError(message(e))
    } finally {
      setAsking(false)
    }
  }

  function decide(request: PlannerBookingIn, accept: boolean) {
    if (session === null) return
    const entry = { booking_id: request.booking_id, decision: accept ? 'accepted' as const : 'rejected' as const, verdict: verdict?.text ?? null }
    setVerdict(null)
    const log = [...session.log, entry]
    if (accept) void replan({ ...session, bookings: [...session.bookings, request], log })
    else store({ ...session, log })
  }

  function toggleOnBoard(id: string) {
    if (session === null) return
    const bookings = session.bookings.map((b) => (b.booking_id === id ? { ...b, on_board: !b.on_board } : b))
    void replan({ ...session, bookings })
  }

  async function moveTo(slot: string) {
    if (session === null || selected === null || busy) return
    latest.current += 1  // a plan still on its way must not undo this move
    setError(null)
    try {
      const result = await api.plannerMove(stateOf(session), selected, slot)
      setPlan(result)
      setMoved(result.moved)
      store({ ...session, placements: result.placements })
      setSelected(null)
    } catch (e) {
      setError(message(e))
    }
  }

  async function download(format: 'pdf' | 'csv') {
    if (session === null) return
    try {
      const blob = await api.exportPlan({ source: 'planner', plan_key: 'planner', state: stateOf(session) }, format)
      downloadBlob(blob, `roro-planner.${format}`)
    } catch (e) {
      setError(message(e))
    }
  }

  function saveSession() {
    if (session === null) return
    downloadBlob(new Blob([JSON.stringify(session, null, 2)], { type: 'application/json' }), 'roro-planner-session.json')
  }

  async function openSession(file: File | undefined) {
    if (file === undefined) return
    const parsed = parseSessionFile(await file.text())
    if (parsed === null) { setError('This file is not a planner session saved by this app.'); return }
    setRowErrors([])
    setWarnings([])
    await replan(parsed)
  }

  const shownPlacements = plan?.placements ?? session?.placements ?? {}
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
      {plan?.warnings?.map((w) => <p key={w} className="notice small">{w}</p>)}
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
          <div className="row">
            <button disabled={session === null || session.bookings.length === 0} onClick={saveSession}>Save session (.json)</button>
            <button disabled={session === null || session.bookings.length === 0} onClick={startOver}>Start over</button>
          </div>
          <label className="field">
            <span>Open a saved session</span>
            <input type="file" accept=".json,application/json" aria-label="Open session" onChange={(e) => void openSession(e.target.files?.[0])} />
          </label>
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
                {moved.length > 0 && <p className="notice small">Moved: {moved.join(', ')}</p>}
                {selected && (
                  <div className="stack">
                    <p className="small">Move {selected} to:</p>
                    <div className="row">
                      {plan.deck.lanes.flatMap((lane) => Array.from({ length: plan.deck.zones }, (_, z) => `${lane.id}-Z${z}`)).map((slot) => (
                        <button key={slot} aria-label={`Zone ${slot}`} onClick={() => void moveTo(slot)}>{slot}</button>
                      ))}
                      <button onClick={() => setSelected(null)}>Cancel</button>
                    </div>
                  </div>
                )}
                <StabilityView deck={plan.deck} />
                <div className="row">
                  <button disabled={busy} onClick={() => void download('pdf')}>Download PDF</button>
                  <button disabled={busy} onClick={() => void download('csv')}>Download CSV</button>
                </div>
              </section>
              {session && (
                <RequestPanel demand={session.demand} onDemand={changeDemand} verdict={verdict} asking={asking}
                  onAsk={(r) => void ask(r)} onDecide={decide} />
              )}
              {session && session.log.length > 0 && (
                <section className="card">
                  <h2>Decisions</h2>
                  <ul>{session.log.map((e, i) => <li key={i}>{e.booking_id}: {e.decision}{e.verdict ? ` (advisor: ${e.verdict})` : ''}</li>)}</ul>
                </section>
              )}
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
          {session && session.bookings.length > 0 && (
            <section className="card">
              <h2>Bookings</h2>
              <div className="table-wrap table-scroll">
                <table>
                  <thead><tr><th>Booking</th><th>Customer</th><th>Unit</th><th className="num">Length</th><th>Zone</th><th>On board</th><th>Move</th></tr></thead>
                  <tbody>
                    {(session?.bookings ?? []).map((b) => {
                      const zone = shownPlacements[b.booking_id]
                      return (
                        <tr key={b.booking_id}>
                          <td>{b.booking_id}</td><td>{b.customer}</td><td>{b.unit_type}</td>
                          <td className="num">{b.length_m}</td><td>{zone ?? 'excluded'}</td>
                          <td><input type="checkbox" aria-label={`${b.booking_id} on board`} checked={b.on_board}
                            disabled={busy || (zone === undefined && !b.on_board)} onChange={() => toggleOnBoard(b.booking_id)} /></td>
                          <td>{zone !== undefined && !b.on_board && (
                            <button aria-label={`Select ${b.booking_id}`} disabled={busy} onClick={() => setSelected(b.booking_id)}>Move</button>
                          )}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      </div>
    </>
  )
}
