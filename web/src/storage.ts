import type { SavedGame } from './types'

const KEY = 'roro-game'
// Kept in memory too, so the reveal still finds the game when browser storage is blocked.
let memory: SavedGame | null = null

export function loadGame(): SavedGame | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw === null ? memory : (JSON.parse(raw) as SavedGame)
  } catch {
    return memory
  }
}

export function saveGame(game: SavedGame): void {
  memory = game
  try {
    localStorage.setItem(KEY, JSON.stringify(game))
  } catch {
    // Storage can be blocked or full: the game still works for this page view.
  }
}

export function clearGame(): void {
  memory = null
  try {
    localStorage.removeItem(KEY)
  } catch {
    // Same as above.
  }
}
