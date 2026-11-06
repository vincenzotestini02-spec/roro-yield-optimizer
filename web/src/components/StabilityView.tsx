import type { Deck } from '../types'

function Meter({ label, value, limit, text }: { label: string; value: number; limit: number; text: string }) {
  const share = limit > 0 ? Math.min(Math.abs(value) / limit, 1) : 0
  return (
    <div>
      <div className="row small" style={{ justifyContent: 'space-between' }}>
        <span>{label}</span><span>{text}</span>
      </div>
      <div className="progress"><div style={{ width: `${share * 100}%` }} /></div>
    </div>
  )
}

export function StabilityView({ deck }: { deck: Deck }) {
  const heelSide = deck.heel_deg > 0 ? 'starboard' : deck.heel_deg < 0 ? 'port' : 'level'
  const trimSide = deck.trim_m > 0 ? 'by the bow' : deck.trim_m < 0 ? 'by the stern' : 'level'
  const tanks = [['Port', deck.ballast.port_t], ['Starboard', deck.ballast.stbd_t],
    ['Fore', deck.ballast.fore_t], ['Aft', deck.ballast.aft_t]] as const
  return (
    <div className="stack">
      <h3>Stability</h3>
      <Meter label="Heel" value={deck.heel_deg} limit={deck.max_heel_deg}
        text={`${Math.abs(deck.heel_deg).toFixed(1)}° ${heelSide} / limit ${deck.max_heel_deg}°`} />
      <Meter label="Trim" value={deck.trim_m} limit={deck.max_trim_m}
        text={`${Math.abs(deck.trim_m).toFixed(2)} m ${trimSide} / limit ${deck.max_trim_m} m`} />
      <p className="small muted">
        Ballast {deck.ballast_total_t.toFixed(0)} t: {tanks.map(([name, t]) => `${name} ${t.toFixed(0)}`).join(' · ')} (tank limit {deck.tank_cap_t} t)
      </p>
    </div>
  )
}
