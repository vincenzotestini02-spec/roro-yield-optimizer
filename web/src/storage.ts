import type { SavedGame } from './types'

const KEY = 'roro-game'

export function loadGame(): SavedGame | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw === null ? null : (JSON.parse(raw) as SavedGame)
  } catch {
    return null
  }
}

export function saveGame(game: SavedGame): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(game))
  } catch {
    // Storage can be blocked or full: the game still works for this page view.
  }
}

export function clearGame(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // Same as above.
  }
}
