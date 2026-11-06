import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { euro } from '../format'
import type { DemandTable } from '../types'

export function DemandPage() {
  const [table, setTable] = useState<DemandTable | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.demandTable().then(setTable).catch((e) => setError(e instanceof ApiError ? e.detail : 'Something went wrong.'))
  }, [])

  return (
    <>
      <div className="stack">
        <h1>When does optimizing pay off?</h1>
        <p className="muted">The game's deck of 600 lane-metres at three demand levels. The fuller the ship, the more each decision matters.</p>
      </div>
      {error && <p className="notice">{error}</p>}
      {table && (
        <section className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Demand</th><th className="num">Requests</th><th className="num">Demand / deck</th><th className="num">FCFS</th>
                  <th className="num">Smart planner</th><th className="num">Vs FCFS</th><th className="num">Lost to FCFS</th><th className="num">Perfect foresight</th>
                </tr>
              </thead>
              <tbody>
                {table.levels.map((l) => (
                  <tr key={l.label}>
                    <td>{l.label}</td>
                    <td className="num">{l.n_requests}</td>
                    <td className="num">{(l.demand_ratio * 100).toFixed(0)}%</td>
                    <td className="num">{euro(l.fcfs)}</td>
                    <td className="num">{euro(l.smart)}</td>
                    <td className="num">{l.smart_vs_fcfs_pct >= 0 ? '+' : '−'}{Math.abs(l.smart_vs_fcfs_pct).toFixed(1)}%</td>
                    <td className="num">{l.lost_to_fcfs} of {l.n_sailings}</td>
                    <td className="num">{euro(l.optimal)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted">Mean score over sailings {table.seeds[0]} to {table.seeds[1]}, with {table.k} sampled futures per request.</p>
          <p>Tighter decks raise the percentage gain, not total profit. All results come from synthetic sailings.</p>
        </section>
      )}
    </>
  )
}
