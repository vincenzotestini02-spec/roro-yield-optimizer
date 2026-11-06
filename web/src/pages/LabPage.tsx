import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, pollJob } from '../api'
import { DeckView } from '../components/DeckView'
import { JobProgress } from '../components/JobProgress'
import { euro, pctAgainst } from '../format'
import type { LabDefaults, LabPlans, LabSmart, LabValues, PlanResult } from '../types'

const FIELDS: { title: string; items: [string, string, number][] }[] = [
  { title: 'Demand', items: [
    ['n_requests', 'Booking requests', 1],
    ['contract_share', 'Contract share of requests', 0.05],
    ['spot_rate_multiplier', 'Spot price level (×)', 0.05],
    ['contract_floor_share', 'Guaranteed contract metres (share of deck)', 0.05],
  ] },
  { title: 'Vessel', items: [
    ['n_lanes', 'Lanes', 1],
    ['lane_length_m', 'Lane length (m)', 1],
    ['max_dwt_t', 'Max cargo deadweight (t)', 10],
    ['reefer_plugs', 'Reefer plugs', 1],
    ['lashing_gap_m', 'Lashing gap between units (m)', 0.1],
  ] },
  { title: 'Stability', items: [
    ['max_heel_deg', 'Max heel (°)', 0.1],
    ['max_trim_m', 'Max trim (m)', 0.05],
    ['ballast_tank_cap_t', 'Ballast tank capacity (t per tank)', 10],
    ['ballast_cost_per_t', 'Ballast cost (€/t)', 0.5],
  ] },
  { title: 'Sailing', items: [['seed', 'Random seed', 1]] },
]

const ROWS: [string, (p: PlanResult) => string][] = [
  ['Score (margin − penalty − ballast)', (p) => euro(p.kpis.objective)],
  ['Revenue', (p) => euro(p.kpis.revenue)],
  ['RevPAL, €/lm', (p) => p.kpis.revpal.toFixed(1)],
  ['Deck utilisation', (p) => `${p.kpis.deck_util_pct.toFixed(0)}%`],
  ['Deadweight used', (p) => `${p.kpis.dwt_pct.toFixed(0)}%`],
  ['Reefer plugs used', (p) => String(p.kpis.plugs_used)],
  ['Units loaded', (p) => String(p.kpis.n_accepted)],
  ['Contract shortfall, m', (p) => p.kpis.shortfall_m.toFixed(0)],
  ['Ballast, t', (p) => p.kpis.ballast_t.toFixed(0)],
  ['Heel, °', (p) => p.kpis.heel_deg.toFixed(1)],
  ['Trim, m', (p) => p.kpis.trim_m.toFixed(2)],
]

function message(e: unknown): string {
  return e instanceof ApiError ? e.detail : 'Something went wrong.'
}

function Bars({ plans }: { plans: PlanResult[] }) {
  const top = Math.max(1, ...plans.map((p) => p.sold_m.contract + p.sold_m.spot))
  return (
    <div className="bars" aria-label="Lane-metres sold, by segment">
      {plans.map((p) => (
        <div className="bar-row" key={p.method}>
          <span>{p.method}</span>
          <div className="bar-track">
            <div className="contract" style={{ width: `${(p.sold_m.contract / top) * 100}%` }} />
            <div className="spot" style={{ width: `${(p.sold_m.spot / top) * 100}%` }} />
          </div>
          <span className="small">{(p.sold_m.contract + p.sold_m.spot).toFixed(0)} m</span>
        </div>
      ))}
      <p className="small muted"><span className="tag contract">contract</span> <span className="tag spot">spot</span></p>
    </div>
  )
}

export function LabPage() {
  const [defaults, setDefaults] = useState<LabDefaults | null>(null)
  const [values, setValues] = useState<LabValues>({})
  const [plans, setPlans] = useState<LabPlans | null>(null)
  const [ranValues, setRanValues] = useState<LabValues>({})
  const [smart, setSmart] = useState<LabSmart | null>(null)
  const [computing, setComputing] = useState(false)
  const [smartProgress, setSmartProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const smartRun = useRef<{ id: string; abort: AbortController } | null>(null)

  const compare = useCallback(async (params: LabValues) => {
    setComputing(true)
    setError(null)
    setSmart(null)
    try {
      const { job_id } = await api.labPlans(params)
      setPlans(await pollJob<LabPlans>(job_id, () => {}))
      setRanValues(params)
    } catch (e) {
      setError(message(e))
    } finally {
      setComputing(false)
    }
  }, [])

  useEffect(() => {
    api.labDefaults()
      .then((d) => { setDefaults(d); setValues(d.values); return compare(d.values) })
      .catch((e) => setError(message(e)))
  }, [compare])

  async function runSmart() {
    const abort = new AbortController()
    setError(null)
    setSmartProgress(0)
    try {
      const { job_id } = await api.labSmart(ranValues)
      smartRun.current = { id: job_id, abort }
      setSmart(await pollJob<LabSmart>(job_id, setSmartProgress, abort.signal))
    } catch (e) {
      if (!abort.signal.aborted) setError(message(e))
    } finally {
      setSmartProgress(null)
      smartRun.current = null
    }
  }

  function cancelSmart() {
    const run = smartRun.current
    if (run === null) return
    run.abort.abort()
    setSmartProgress(null)
    void api.cancelJob(run.id).catch(() => {})
  }

  async function download() {
    try {
      const blob = await api.manifestCsv(ranValues, 'optimal')
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = 'manifest.csv'
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (e) {
      setError(message(e))
    }
  }

  const best = smart?.best ?? plans?.optimal
  const shown = plans === null || best === undefined ? [] : [plans.fcfs, ...(smart ? [smart.smart] : []), best]
  const gain = plans && best ? pctAgainst(best.kpis.objective, plans.fcfs.kpis.objective) : null

  return (
    <>
      <div className="stack">
        <h1>The Lab: change the rules</h1>
        <p className="muted">Move the sliders and see how much an optimizer earns over first come, first served.</p>
      </div>
      <div className="grid-2">
        <section className="card" aria-label="Lab settings">
          {defaults && FIELDS.map(({ title, items }) => {
            const present = items.filter(([name]) => name in defaults.limits)
            return present.length === 0 ? null : (
              <div className="stack" key={title}>
                <h3>{title}</h3>
                {present.map(([name, label, step]) => (
                  <label className="field" key={name}>
                    <span>{label}<strong>{values[name]}</strong></span>
                    <input type="range" min={defaults.limits[name][0]} max={defaults.limits[name][1]} step={step}
                      value={values[name]} onChange={(e) => setValues({ ...values, [name]: Number(e.target.value) })} />
                  </label>
                ))}
              </div>
            )
          })}
          <button className="primary" disabled={computing || defaults === null} onClick={() => void compare(values)}>Compare plans</button>
          <p className="small muted">Hull constants are fixed. Only the end-tank arm follows the lane length.</p>
        </section>
        <div className="stack">
          {error && <p className="notice">{error}</p>}
          {computing && <p className="muted">Optimising…</p>}
          {plans && best && (
            <>
              <div className="grid-3">
                <div className="card"><span className="small muted">Optimizer gain vs FCFS</span><span className="value">{gain ?? 'n/a'}</span></div>
                <div className="card"><span className="small muted">Extra margin per sailing</span><span className="value">{euro(best.kpis.objective - plans.fcfs.kpis.objective)}</span></div>
                <div className="card"><span className="small muted">RevPAL, best possible</span><span className="value">€{best.kpis.revpal.toFixed(1)}/lm</span></div>
              </div>
              {smartProgress !== null
                ? <JobProgress label="The smart planner is playing this sailing" progress={smartProgress} onCancel={cancelSmart} />
                : !smart && <div><button onClick={() => void runSmart()}>Run the smart planner (K = {defaults?.advisor_k} futures per request)</button></div>}
              <div className="card table-wrap">
                <table>
                  <thead><tr><th>Measure</th>{shown.map((p) => <th key={p.method}>{p.method}</th>)}</tr></thead>
                  <tbody>
                    {ROWS.map(([name, read]) => <tr key={name}><td>{name}</td>{shown.map((p) => <td key={p.method}>{read(p)}</td>)}</tr>)}
                  </tbody>
                </table>
              </div>
              <div className="card"><h2>Best possible deck</h2><DeckView deck={best.deck} /></div>
              <div className="card"><h2>Lane-metres sold</h2><Bars plans={shown} /></div>
              <div><button onClick={() => void download()}>Download loading manifest (CSV)</button></div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
