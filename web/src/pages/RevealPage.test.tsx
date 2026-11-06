import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { api, pollJob } from '../api'
import { saveGame } from '../storage'
import { booking, gameState, planResult, verdict } from '../test/fixtures'
import { RevealPage } from './RevealPage'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { gameState: vi.fn(), reveal: vi.fn(), bestPlan: vi.fn() },
  pollJob: vi.fn(),
}))

const pollMock = vi.mocked(pollJob)
const show = () => render(<MemoryRouter><RevealPage /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
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
  localStorage.clear()
  show()
  await screen.findByRole('link', { name: /play a sailing/i })
})
