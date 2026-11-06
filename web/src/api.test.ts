import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError, pollJob } from './api'

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status }))
}
afterEach(() => vi.restoreAllMocks())

test('ApiError carries the server detail', async () => {
  mockFetch(429, { detail: 'The server is busy. Try again in a moment.' })
  await expect(api.gameState(1, [])).rejects.toMatchObject({ status: 429, detail: expect.stringContaining('busy') })
})

test('a validation list from the server becomes readable text', async () => {
  mockFetch(422, { detail: [{ msg: 'Input should be at least 1' }] })
  const error = await api.gameState(0, []).catch((e: ApiError) => e)
  expect((error as ApiError).detail).toContain('at least 1')
})

test('pollJob reports progress and returns the result', async () => {
  vi.useFakeTimers()
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'running', progress: 0.5, result: null, error: null })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'done', progress: 1, result: 42, error: null })))
  const seen: number[] = []
  const promise = pollJob<number>('x', (p) => seen.push(p))
  await vi.runAllTimersAsync()
  await expect(promise).resolves.toBe(42)
  expect(seen).toContain(0.5)
  vi.useRealTimers()
})

test('pollJob rejects when the job failed', async () => {
  mockFetch(200, { status: 'failed', progress: 0, result: null, error: 'The calculation failed. Try again.' })
  await expect(pollJob('x', () => {})).rejects.toMatchObject({ detail: expect.stringContaining('failed') })
})
