export interface Decision {
  booking_id: string
  action: 'accept' | 'reject'
  slot: string | null
}

export interface Booking {
  id: string
  segment: 'contract' | 'spot'
  customer: string
  unit_type: string
  unit_label: string
  length_m: number
  weight_t: number
  is_reefer: boolean
  rate_per_m: number
  revenue: number
  margin: number
}

export interface Placement {
  booking_id: string
  slot: string
  booking: Booking
}

export interface Deck {
  vessel: string
  route: string
  zones: number
  lanes: { id: string; length_m: number; y_m: number }[]
  placements: Placement[]
  remaining_m: Record<string, number>
  used_m: number
  capacity_m: number
  weight_t: number
  max_dwt_t: number
  plugs_used: number
  reefer_plugs: number
  heel_deg: number
  trim_m: number
  max_heel_deg: number
  max_trim_m: number
  ballast: { port_t: number; stbd_t: number; fore_t: number; aft_t: number }
  ballast_total_t: number
  tank_cap_t: number
}

export interface GameState {
  seed: number
  index: number
  n_total: number
  finished: boolean
  current: Booking | null
  past: Booking[]
  deck: Deck
  feasible_slots: string[]
  best_slot: string | null
  cannot_load_reason: string | null
  floor_at_risk: boolean
  contract_floor_m: number
  shortfall_penalty_per_m: number
}

export interface Verdict {
  booking_id: string
  accept: boolean
  feasible: boolean
  n_pays_off: number
  k: number
  expected_gain_eur: number
  reason: string | null
  text: string
}

export interface Kpis {
  method: string
  n_accepted: number
  revenue: number
  margin: number
  shortfall_m: number
  penalty: number
  objective: number
  revpal: number
  deck_util_pct: number
  dwt_pct: number
  plugs_used: number
  contract_m: number
  ballast_t: number
  ballast_cost: number
  heel_deg: number
  trim_m: number
}

export interface PlanResult {
  method: string
  kpis: Kpis
  deck: Deck
  rejected: Booking[]
  sold_m: { contract: number; spot: number }
}

export interface RevealResult {
  you: PlanResult
  fcfs: PlanResult
  smart_job: string
}

export interface CostlyDecision {
  booking_id: string | null
  kind: string
  impact_eur: number
  reason: string
}

export interface BestResult {
  plan: PlanResult
  costly: CostlyDecision[]
}

export type LabValues = Record<string, number>

export interface LabDefaults {
  values: LabValues
  limits: Record<string, [number, number]>
  advisor_k: number
}

export interface LabPlans {
  fcfs: PlanResult
  optimal: PlanResult
}

export interface LabSmart {
  smart: PlanResult
  best: PlanResult
}

export interface DemandLevel {
  label: string
  n_requests: number
  demand_ratio: number
  fcfs: number
  smart: number
  optimal: number
  smart_vs_fcfs_pct: number
  smart_vs_fcfs_se_eur: number
  lost_to_fcfs: number
  n_sailings: number
}

export interface DemandTable {
  levels: DemandLevel[]
  k: number
  seeds: [number, number]
  generated_at: string
}

export interface SavedGame {
  seed: number
  decisions: Decision[]
  verdicts: Record<string, Verdict>
}
