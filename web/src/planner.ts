import type { PlannerSession } from './types'

const KEY = 'roro-planner'
// Kept in memory too, so the page still works when browser storage is blocked.
let memory: PlannerSession | null = null

function isSession(value: unknown): value is PlannerSession {
  if (value === null || typeof value !== 'object') return false
  const s = value as Record<string, unknown>
  return typeof s.vessel === 'object' && s.vessel !== null && Array.isArray(s.bookings)
    && typeof s.placements === 'object' && s.placements !== null && Array.isArray(s.log)
    && typeof s.demand === 'object' && s.demand !== null
    && (s.bookings as unknown[]).every((b) => typeof b === 'object' && b !== null
      && typeof (b as Record<string, unknown>).booking_id === 'string')
}

/** The saved session, and whether something unreadable was found (and cleared). */
export function loadPlanner(): { session: PlannerSession | null; damaged: boolean } {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(KEY)
  } catch {
    return { session: memory, damaged: false }
  }
  if (raw === null) return { session: memory, damaged: false }
  try {
    const parsed: unknown = JSON.parse(raw)
    if (isSession(parsed)) return { session: parsed, damaged: false }
  } catch {
    // fall through to the damaged case
  }
  clearPlanner()
  return { session: null, damaged: true }
}

export function savePlanner(session: PlannerSession): void {
  memory = session
  try {
    localStorage.setItem(KEY, JSON.stringify(session))
  } catch {
    // Storage can be blocked or full: the session still lives for this page view.
  }
}

export function clearPlanner(): void {
  memory = null
  try {
    localStorage.removeItem(KEY)
  } catch {
    // Same as above.
  }
}

/** A session read from a file the user picked, or null if it is not one. */
export function parseSessionFile(text: string): PlannerSession | null {
  try {
    const parsed: unknown = JSON.parse(text)
    return isSession(parsed) ? parsed : null
  } catch {
    return null
  }
}
