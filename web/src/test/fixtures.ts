import type { Booking, Deck, GameState, Kpis, PlanResult, Verdict } from '../types'

export const booking = (id: string, over: Partial<Booking> = {}): Booking => ({
  id, segment: 'spot', customer: 'Spot haulier #1', unit_type: 'semi_trailer', unit_label: 'semi-trailer',
  length_m: 13.6, weight_t: 20, is_reefer: false, rate_per_m: 90, revenue: 1224, margin: 1100, ...over,
})

export const deck = (over: Partial<Deck> = {}): Deck => ({
  vessel: 'MV Nordic Bridge', route: 'Esbjerg → Immingham', zones: 4,
  lanes: [{ id: 'L1', length_m: 120, y_m: -3 }, { id: 'L2', length_m: 120, y_m: 3 }],
  placements: [], remaining_m: {}, used_m: 0, capacity_m: 240, weight_t: 0, max_dwt_t: 1100, plugs_used: 0,
  reefer_plugs: 12, heel_deg: 0, trim_m: 0, max_heel_deg: 2, max_trim_m: 0.5,
  ballast: { port_t: 0, stbd_t: 0, fore_t: 0, aft_t: 0 }, ballast_total_t: 0, tank_cap_t: 300, usable_m: 240, broken_stowage_pct: 0, ...over,
})

export const gameState = (over: Partial<GameState> = {}): GameState => ({
  seed: 5, index: 0, n_total: 60, finished: false, current: booking('B001'), past: [], deck: deck(),
  feasible_slots: ['L1-Z0', 'L2-Z0'], best_slot: 'L1-Z0', cannot_load_reason: null, floor_at_risk: false,
  contract_floor_m: 210, shortfall_penalty_per_m: 200, ...over,
})

export const verdict = (over: Partial<Verdict> = {}): Verdict => ({
  booking_id: 'B001', accept: true, feasible: true, n_pays_off: 15, k: 20, expected_gain_eur: 300, reason: null,
  text: 'Accept — pays off in 15 of 20 futures, expected gain +€300', ...over,
})

export const kpis = (method: string, objective: number): Kpis => ({
  method, n_accepted: 40, revenue: 60000, margin: objective, shortfall_m: 0, penalty: 0, objective, revpal: 83,
  deck_util_pct: 90, dwt_pct: 70, plugs_used: 5, contract_m: 200, ballast_t: 20, ballast_cost: 100, heel_deg: 0.1, trim_m: 0.1,
})

export const planResult = (method: string, objective: number): PlanResult => ({
  method, kpis: kpis(method, objective), deck: deck(), rejected: [], sold_m: { contract: 200, spot: 300 },
})
