import type { Decision, LabValues } from './types'

/** Longest code accepted after `#g=` or `#p=`, so a link stays usable in chats and email. */
export const MAX_FRAGMENT = 4000

type SharedGame = { seed: number; decisions: Decision[] }

function toBase64Url(text: string): string {
  return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function fromBase64Url(code: string): string | null {
  if (code.length > MAX_FRAGMENT || !/^[A-Za-z0-9+/_=-]*$/.test(code)) return null
  const standard = code.replace(/-/g, '+').replace(/_/g, '/')
  try {
    return atob(standard + '='.repeat((4 - (standard.length % 4)) % 4))
  } catch {
    return null
  }
}

function parse(code: string): unknown {
  const text = fromBase64Url(code)
  if (text === null) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export function encodeGame(game: SharedGame): string {
  const code = { accept: 'a', reject: 'r', move: 'm' } as const
  const d = game.decisions.map((x) => [x.booking_id, code[x.action], x.slot])
  return toBase64Url(JSON.stringify({ s: game.seed, d }))
}

export function decodeGame(code: string): SharedGame | null {
  const data = parse(code) as { s?: unknown; d?: unknown } | null
  if (data === null || typeof data !== 'object' || !Number.isInteger(data.s) || !Array.isArray(data.d)) return null
  const decisions: Decision[] = []
  for (const item of data.d) {
    if (!Array.isArray(item) || item.length !== 3) return null
    const [id, act, slot] = item
    const action = act === 'a' ? 'accept' : act === 'r' ? 'reject' : act === 'm' ? 'move' : null
    if (typeof id !== 'string' || action === null || !(slot === null || typeof slot === 'string')) return null
    if (action === 'move' && slot === null) return null
    decisions.push({ booking_id: id, action, slot })
  }
  return { seed: data.s as number, decisions }
}

export function encodeLab(values: LabValues): string {
  return toBase64Url(JSON.stringify(values))
}

export function decodeLab(code: string, limits: Record<string, [number, number]>): LabValues | null {
  const data = parse(code)
  if (data === null || typeof data !== 'object' || Array.isArray(data)) return null
  const values: LabValues = {}
  for (const [name, value] of Object.entries(data as Record<string, unknown>)) {
    const limit = limits[name]
    if (limit && typeof value === 'number' && value >= limit[0] && value <= limit[1]) values[name] = value
  }
  return values
}

export function hashCode(hash: string, key: string): string | null {
  const prefix = `#${key}=`
  return hash.startsWith(prefix) ? hash.slice(prefix.length) : null
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
