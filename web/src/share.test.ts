import { expect, test } from 'vitest'
import { decodeGame, decodeLab, encodeGame, encodeLab, MAX_FRAGMENT } from './share'

const game = {
  seed: 42,
  decisions: [
    { booking_id: 'B001', action: 'accept' as const, slot: null },
    { booking_id: 'B002', action: 'reject' as const, slot: null },
    { booking_id: 'B003', action: 'accept' as const, slot: 'L2-Z3' },
  ],
}

test('a game survives encode and decode', () => {
  expect(decodeGame(encodeGame(game))).toEqual(game)
})

test('a damaged or truncated code gives null', () => {
  const code = encodeGame(game)
  expect(decodeGame('not-a-code')).toBeNull()
  expect(decodeGame(code.slice(0, code.length - 6))).toBeNull()
  expect(decodeGame(btoa(JSON.stringify({ s: 'x', d: [] })))).toBeNull()
  expect(decodeGame(btoa(JSON.stringify({ s: 3, d: [['B1', 'z', null]] })))).toBeNull()
})

test('a code longer than MAX_FRAGMENT is refused', () => {
  expect(decodeGame('a'.repeat(MAX_FRAGMENT + 1))).toBeNull()
})

test('lab values outside the limits are dropped', () => {
  const limits = { n_lanes: [1, 16] as [number, number], seed: [1, 10000] as [number, number] }
  const decoded = decodeLab(encodeLab({ n_lanes: 40, seed: 7, unknown: 3 }), limits)
  expect(decoded).toEqual({ seed: 7 })
})

test('lab values survive encode and decode', () => {
  const limits = { n_lanes: [1, 16] as [number, number] }
  expect(decodeLab(encodeLab({ n_lanes: 4 }), limits)).toEqual({ n_lanes: 4 })
})
