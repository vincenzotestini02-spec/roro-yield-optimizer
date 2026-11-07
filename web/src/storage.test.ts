import { afterEach, expect, test, vi } from 'vitest'
import { clearGame, loadGame, saveGame } from './storage'

afterEach(() => { vi.restoreAllMocks(); clearGame() })

test('a saved game comes back', () => {
  saveGame({ seed: 4, decisions: [], verdicts: {} })
  expect(loadGame()?.seed).toBe(4)
})

test('storage works when localStorage throws', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
  expect(loadGame()).toBeNull()
  expect(() => saveGame({ seed: 1, decisions: [], verdicts: {} })).not.toThrow()
})

test('a blocked storage still hands the game to the next page', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
  saveGame({ seed: 9, decisions: [], verdicts: {} })
  expect(loadGame()?.seed).toBe(9)
})

test('damaged data is ignored', () => {
  localStorage.setItem('roro-game', '{broken')
  expect(loadGame()).toBeNull()
})
