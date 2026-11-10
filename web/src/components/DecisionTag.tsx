import type { Verdict } from '../types'

const LABELS: Record<Verdict['decision'], string> = { accept: 'Accept', reject: 'Reject', your_call: 'Your call' }

export function DecisionTag({ verdict }: { verdict: Verdict }) {
  if (!verdict.feasible) return <span className="tag decision reject">Can't load</span>
  return <span className={`tag decision ${verdict.decision}`}>{LABELS[verdict.decision]}</span>
}
