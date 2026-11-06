export function euro(value: number): string {
  const rounded = Math.round(value)
  return `${rounded < 0 ? '−' : ''}€${Math.abs(rounded).toLocaleString('en-US')}`
}

/** Percentage against a baseline, or null when the baseline is not positive. */
export function pctAgainst(value: number, baseline: number): string | null {
  if (baseline <= 0) return null
  const pct = (value / baseline - 1) * 100
  return `${pct >= 0 ? '+' : '−'}${Math.abs(pct).toFixed(1)}%`
}
