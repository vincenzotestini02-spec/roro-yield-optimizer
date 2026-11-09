import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, pollJob } from '../api'
import { DeckView } from '../components/DeckView'
import { JobProgress } from '../components/JobProgress'
import { downloadBlob } from '../download'
import { copyText, decodeLab, encodeLab, hashCode } from '../share'
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
    ['broken_stowage_pct', 'Lost space (broken stowage)', 0.01],
  ] },
  { title: 'Stability', items: [
    ['max_heel_deg', 'Max heel (°)', 0.1],
    ['max_trim_m', 'Max trim (m)', 0.05],
    ['ballast_tank_cap_t', 'Ballast tank capacity (t per tank)', 10],
    ['ballast_cost_per_t', 'Ballast cost (€/t)', 0.5],
    ['displacement_t', 'Displacement (t)', 500],
    ['gm_m', 'Metacentric height GM (m)', 0.1],
    ['mtc_tm_per_cm', 'Moment to change trim (t·m/cm)', 10],
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
  const [preset, setPreset] = useState('demo')
  const [confirmSlow, setConfirmSlow] = useState(false)
  const [linkError, setLinkError] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  async function share() {
    const url = `${window.location.origin}/lab#p=${encodeLab(ranValues)}`
    setCopied((await copyText(url)) ? 'Link copied.' : url)
  }
  const smartRun = useRef<{ id: string; abort: AbortController } | null>(null)

  const stopSmart = useCallback(() => {
    const run = smartRun.current
    if (run === null) return
    smartRun.current = null
    run.abort.abort()
    setSmartProgress(null)
    void api.cancelJob(run.id)?.catch(() => {})
  }, [])

  const compare = useCallback(async (params: LabValues) => {
    stopSmart()
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
  }, [stopSmart])

  useEffect(() => {
    api.labDefaults()
      .then((d) => {
        setDefaults(d)
        const code = hashCode(window.location.hash, 'p')
        const shared = code === null ? null : decodeLab(code, d.limits)
        if (code !== null && shared === null) setLinkError('This link is damaged or incomplete. Showing the default settings.')
        const start = { ...d.values, ...(shared ?? {}) }
        setValues(start)
        return compare(start)
      })
      .catch((e) => setError(message(e)))
  }, [compare])

  function choosePreset(key: string) {
    if (defaults === null) return
    setPreset(key)
    const next = { ...values, ...defaults.presets[key].values }
    setValues(next)
    void compare(next)
  }

  function askSmart() {
    if (plans?.smart_may_be_slow && !confirmSlow) setConfirmSlow(true)
    else void runSmart()
  }

  async function runSmart() {
    setConfirmSlow(false)
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
      if (smartRun.current?.abort === abort) {
        setSmartProgress(null)
        smartRun.current = null
      }
    }
  }

  const cancelSmart = stopSmart

  async function download(format: 'pdf' | 'csv') {
    try {
      const blob = await api.exportPlan({ source: 'lab', params: ranValues, plan_key: 'optimal' }, format)
      downloadBlob(blob, `roro-plan-optimal.${format}`)
    } catch (e) {
      setError(message(e))
    }
  }

  function shownValue(name: string): string {
    const v = values[name]
    return name === 'broken_stowage_pct' ? `${Math.round(v * 100)}%` : String(v)
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
          {defaults && (
            <label className="field">
              <span>Vessel</span>
              <select aria-label="Vessel" value={preset} onChange={(e) => choosePreset(e.target.value)}>
                {Object.entries(defaults.presets).map(([key, p]) => <option key={key} value={key}>{p.label}</option>)}
              </select>
              <span className="small muted">{defaults.note}</span>
            </label>
          )}
          {defaults && FIELDS.map(({ title, items }) => {
            const present = items.filter(([name]) => name in defaults.limits)
            return present.length === 0 ? null : (
              <div className="stack" key={title}>
                <h3>{title}</h3>
                {present.map(([name, label, step]) => (
                  <label className="field" key={name}>
                    <span>{label}<strong>{shownValue(name)}</strong></span>
                    <input type="range" min={defaults.limits[name][0]} max={defaults.limits[name][1]} step={step}
                      value={values[name]} onChange={(e) => setValues({ ...values, [name]: Number(e.target.value) })} />
                  </label>
                ))}
              </div>
            )
          })}
          <button className="primary" disabled={computing || defaults === null} onClick={() => void compare(values)}>Compare plans</button>
          <p className="small muted">Other hull constants are fixed. The end-tank arm follows the lane length.</p>
        </section>
        <div className="stack">
          {linkError && <p className="notice">{linkError}</p>}
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
                : !smart && <div><button onClick={askSmart}>Run the smart planner (K = {defaults?.advisor_k} futures per request)</button></div>}
              {confirmSlow && (
                <div className="notice stack">
                  <p>On this ship the smart planner can take several minutes on the free server.</p>
                  <div className="row"><button onClick={() => void runSmart()}>Run anyway</button><button onClick={() => setConfirmSlow(false)}>Not now</button></div>
                </div>
              )}
              <div className="card table-wrap">
                <table>
                  <thead><tr><th>Measure</th>{shown.map((p) => <th key={p.method}>{p.method}</th>)}</tr></thead>
                  <tbody>
                    {ROWS.map(([name, read]) => <tr key={name}><td>{name}</td>{shown.map((p) => <td key={p.method}>{read(p)}</td>)}</tr>)}
                  </tbody>
                </table>
              </div>
              <div className="card">
                <h2>Best possible deck</h2>
                <DeckView deck={best.deck} />
                <p className="small muted">Usable {best.deck.usable_m.toFixed(0)} of {best.deck.capacity_m.toFixed(0)} lane-m after lost space.</p>
              </div>
              <div className="card"><h2>Lane-metres sold</h2><Bars plans={shown} /></div>
              <div className="row">
                <button onClick={() => void download('pdf')}>Download PDF</button>
                <button onClick={() => void download('csv')}>Download CSV</button>
                <button onClick={() => void share()}>Copy share link</button>
              </div>
              {copied && <p className="small muted" style={{ wordBreak: 'break-all' }}>{copied}</p>}
            </>
          )}
        </div>
      </div>
    </>
  )
}
