import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { api, pollJob } from '../api'
import { clearGame, loadGame, saveGame } from '../storage'
import { encodeGame } from '../share'
import { booking, gameState, planResult, verdict } from '../test/fixtures'
import { RevealPage } from './RevealPage'

vi.mock('../download', () => ({ downloadBlob: vi.fn() }))

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { gameState: vi.fn(), reveal: vi.fn(), bestPlan: vi.fn(), exportPlan: vi.fn() },
  pollJob: vi.fn(),
}))

const pollMock = vi.mocked(pollJob)
const show = (path = '/reveal') => render(<MemoryRouter initialEntries={[path]}><RevealPage /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  clearGame()
  saveGame({
    seed: 3,
    decisions: [
      { booking_id: 'B1', action: 'reject', slot: null },
      { booking_id: 'B2', action: 'reject', slot: null },
    ],
    verdicts: { B1: verdict({ booking_id: 'B1' }) },
  })
  vi.mocked(api.gameState).mockResolvedValue(gameState({ finished: true, current: null, past: [booking('B1'), booking('B2')] }))
  vi.mocked(api.reveal).mockResolvedValue({ you: planResult('You', 1000), fcfs: planResult('FCFS', 2000), smart_job: 's1' })
  vi.mocked(api.bestPlan).mockResolvedValue({ job_id: 'b1' })
})

test('You and FCFS show at once while Smart shows progress', async () => {
  pollMock.mockImplementation((_id, onProgress) => { onProgress(0.25); return new Promise(() => {}) })
  show()
  await screen.findByText('€1,000')
  expect(screen.getByText('€2,000')).toBeInTheDocument()
  await screen.findByRole('progressbar')
})

test('the optimizer card appears after the smart plan', async () => {
  pollMock.mockResolvedValueOnce(planResult('Smart planner', 3000))
  pollMock.mockResolvedValueOnce({ plan: planResult('Optimizer', 4000), costly: [] })
  show()
  await screen.findByText('€3,000')
  await screen.findByText('€4,000')
})

test('a failed smart plan still shows the best plan', async () => {
  pollMock.mockRejectedValueOnce(new Error('failed'))
  pollMock.mockResolvedValueOnce({ plan: planResult('Optimizer', 4000), costly: [] })
  show()
  await screen.findByText('€4,000')
  expect(screen.getByText(/Unavailable for this sailing/)).toBeInTheDocument()
})

test('the advisor table lists one row per request, with a mark when you disagreed', async () => {
  pollMock.mockImplementation(() => new Promise(() => {}))
  show()
  const row = (await screen.findByText(/^B1 /)).closest('tr') as HTMLElement
  expect(row).toHaveTextContent('reject')
  expect(row).toHaveTextContent('accept')
  expect(row).toHaveTextContent('15/20')
  expect(row).toHaveTextContent('✗')
  expect((screen.getByText(/^B2 /).closest('tr') as HTMLElement)).toHaveTextContent('n/a')
})

test('costly decisions are listed', async () => {
  pollMock.mockResolvedValueOnce(planResult('Smart planner', 3000))
  pollMock.mockResolvedValueOnce({
    plan: planResult('Optimizer', 4000),
    costly: [{ booking_id: 'B7', kind: 'rejected_optimal', impact_eur: 500, reason: 'worth more than it looked' }],
  })
  show()
  await screen.findByText(/worth more than it looked/)
})

test('without a finished game the page points back to the game', async () => {
  clearGame()
  show()
  await screen.findByRole('link', { name: /play a sailing/i })
})

test('a shared link shows the shared result and keeps the viewer game', async () => {
  pollMock.mockImplementation(() => new Promise(() => {}))
  saveGame({ seed: 77, decisions: [], verdicts: {} })
  const code = encodeGame({ seed: 3, decisions: [{ booking_id: 'B1', action: 'reject', slot: null }] })
  show(`/reveal#g=${code}`)
  await screen.findByText(/Shared result/)
  expect(vi.mocked(api.reveal)).toHaveBeenCalledWith(3, [{ booking_id: 'B1', action: 'reject', slot: null }])
  expect(loadGame()?.seed).toBe(77)
})

test('a damaged link shows a message and a way back to the game', async () => {
  show('/reveal#g=@@broken')
  await screen.findByText(/This link is damaged or incomplete/)
  expect(screen.getByRole('link', { name: /play a sailing/i })).toBeInTheDocument()
})

test('copy share link puts a #g= url on the clipboard', async () => {
  pollMock.mockImplementation(() => new Promise(() => {}))
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  show()
  await screen.findByText('€1,000')
  screen.getByRole('button', { name: 'Copy share link' }).click()
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining('/reveal#g=')))
})

test('export buttons download the plan on screen', async () => {
  pollMock.mockImplementation(() => new Promise(() => {}))
  vi.mocked(api.exportPlan).mockResolvedValue(new Blob(['x']))
  show()
  await screen.findByText('€1,000')
  screen.getByRole('button', { name: 'Download PDF' }).click()
  await waitFor(() => expect(api.exportPlan).toHaveBeenCalledWith(expect.objectContaining({ source: 'game', plan_key: 'fcfs', seed: 3 }), 'pdf'))
})

test('the reveal table shows your call', async () => {
  pollMock.mockImplementation(() => new Promise(() => {}))
  saveGame({
    seed: 3, decisions: [{ booking_id: 'B1', action: 'reject', slot: null }, { booking_id: 'B2', action: 'reject', slot: null }],
    verdicts: { B1: verdict({ booking_id: 'B1', decision: 'your_call' }) },
  })
  show()
  const row = (await screen.findByText(/^B1 /)).closest('tr') as HTMLElement
  expect(row).toHaveTextContent('your call')
})

test('the reveal shows that the smart planner knew n', async () => {
  pollMock.mockImplementation(() => new Promise(() => {}))
  vi.mocked(api.reveal).mockResolvedValue({
    you: planResult('You', 1000), fcfs: planResult('FCFS', 2000), smart_job: 's1',
    notes: ['The smart planner knew how many requests the sailing would get.'],
  })
  show()
  await screen.findByText(/knew how many requests/)
})
