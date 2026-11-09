import { useState } from 'react'
import type { Demand, PlannerBookingIn, PlannerVerdict } from '../types'

const UNITS: Record<string, { label: string; length: number; weight: number }> = {
  semi_trailer: { label: 'Semi-trailer', length: 13.6, weight: 22 },
  accompanied_truck: { label: 'Accompanied truck', length: 16.5, weight: 30 },
  mafi: { label: 'Mafi roll-trailer', length: 12.2, weight: 40 },
  van: { label: 'Van', length: 6.5, weight: 3 },
  car_batch: { label: 'Car batch', length: 4.8, weight: 1.6 },
}

export function assumptionText(d: Demand): string {
  return `Assumption: ${d.level} demand, ${Math.round(d.contract_share * 100)}% contract`
}

interface Props {
  demand: Demand
  onDemand: (d: Demand) => void
  verdict: PlannerVerdict | null
  asking: boolean
  onAsk: (request: PlannerBookingIn) => void
  onDecide: (request: PlannerBookingIn, accept: boolean) => void
}

export function RequestPanel({ demand, onDemand, verdict, asking, onAsk, onDecide }: Props) {
  const [id, setId] = useState('')
  const [customer, setCustomer] = useState('')
  const [unit, setUnit] = useState('semi_trailer')
  const [length, setLength] = useState(UNITS.semi_trailer.length)
  const [weight, setWeight] = useState(UNITS.semi_trailer.weight)
  const [segment, setSegment] = useState<'contract' | 'spot'>('spot')
  const [price, setPrice] = useState('')
  const [reefer, setReefer] = useState(false)
  const [port, setPort] = useState('Immingham')

  function chooseUnit(key: string) {
    setUnit(key)
    setLength(UNITS[key].length)
    setWeight(UNITS[key].weight)
  }

  const priceValue = Number(price.replace(',', '.'))
  const ready = id.trim() !== '' && customer.trim() !== '' && price.trim() !== '' && priceValue > 0
  const request: PlannerBookingIn = {
    booking_id: id.trim(), customer: customer.trim(), unit_type: unit, length_m: length, weight_t: weight,
    discharge_port: port.trim() || 'Immingham', segment, is_reefer: reefer, rate_per_m: ready ? priceValue : null,
    reefer_fee: null, height_m: null, axle_count: null, on_board: false,
  }

  function decide(accept: boolean) {
    onDecide(request, accept)
    setId('')
    setPrice('')
  }

  return (
    <section className="card" aria-label="New request">
      <h2>New request</h2>
      <p className="small"><strong>{assumptionText(demand)}</strong></p>
      <div className="grid-2-tight">
        <label className="field"><span>Booking id</span><input aria-label="Booking id" value={id} onChange={(e) => setId(e.target.value)} /></label>
        <label className="field"><span>Customer</span><input aria-label="Customer" value={customer} onChange={(e) => setCustomer(e.target.value)} /></label>
        <label className="field"><span>Unit type</span>
          <select aria-label="Unit type" value={unit} onChange={(e) => chooseUnit(e.target.value)}>
            {Object.entries(UNITS).map(([key, u]) => <option key={key} value={key}>{u.label}</option>)}
          </select>
        </label>
        <label className="field"><span>Segment</span>
          <select aria-label="Segment" value={segment} onChange={(e) => setSegment(e.target.value as 'contract' | 'spot')}>
            <option value="spot">Spot</option><option value="contract">Contract</option>
          </select>
        </label>
        <label className="field"><span>Length (m)</span><input aria-label="Length (m)" type="number" min={1} max={25} step={0.1} value={length} onChange={(e) => setLength(Number(e.target.value))} /></label>
        <label className="field"><span>Weight (t)</span><input aria-label="Weight (t)" type="number" min={0.1} max={80} step={0.1} value={weight} onChange={(e) => setWeight(Number(e.target.value))} /></label>
        <label className="field"><span>Price per metre (€)</span><input aria-label="Price per metre (€)" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
        <label className="field"><span>Discharge port</span><input aria-label="Discharge port" value={port} onChange={(e) => setPort(e.target.value)} /></label>
      </div>
      <label className="row small"><input type="checkbox" aria-label="Reefer" checked={reefer} onChange={(e) => setReefer(e.target.checked)} /> Needs a reefer plug</label>
      <details>
        <summary>Demand assumption</summary>
        <div className="grid-2-tight">
          <label className="field"><span>Demand level</span>
            <select aria-label="Demand level" value={demand.level} onChange={(e) => onDemand({ ...demand, level: e.target.value as Demand['level'] })}>
              <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option>
            </select>
          </label>
          <label className="field"><span>Contract share<strong>{Math.round(demand.contract_share * 100)}%</strong></span>
            <input aria-label="Contract share" type="range" min={0} max={0.9} step={0.05} value={demand.contract_share}
              onChange={(e) => onDemand({ ...demand, contract_share: Number(e.target.value) })} />
          </label>
          <label className="field"><span>Hours to departure</span>
            <input aria-label="Hours to departure" type="number" min={0} max={1440} value={demand.hours_to_departure}
              onChange={(e) => onDemand({ ...demand, hours_to_departure: Number(e.target.value) })} />
          </label>
          <label className="field"><span>Booking window (days)</span>
            <input aria-label="Booking window (days)" type="number" min={1} max={60} value={demand.window_days}
              onChange={(e) => onDemand({ ...demand, window_days: Number(e.target.value) })} />
          </label>
        </div>
      </details>
      <div className="row">
        <button className="primary" disabled={!ready || asking} onClick={() => onAsk(request)}>Ask the advisor</button>
        {asking && <span className="small muted">The advisor is playing out possible futures…</span>}
      </div>
      {verdict && verdict.booking_id === request.booking_id && (
        <div className="stack">
          <p><strong>Advisor:</strong> {verdict.text}</p>
          <p className="small muted">{verdict.assumption}</p>
          <div className="row">
            <button className="primary" onClick={() => decide(true)}>Accept request</button>
            <button onClick={() => decide(false)}>Reject request</button>
          </div>
        </div>
      )}
    </section>
  )
}
