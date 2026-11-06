import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError } from '../api'
import { DemandPage } from './DemandPage'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { demandTable: vi.fn() },
}))

const level = (label: string, n: number, lost: number) => ({
  label, n_requests: n, demand_ratio: n / 46, fcfs: 40000, smart: 41000, optimal: 45000,
  smart_vs_fcfs_pct: 2.5, smart_vs_fcfs_se_eur: 300, lost_to_fcfs: lost, n_sailings: 30,
})

beforeEach(() => {
  vi.mocked(api.demandTable).mockResolvedValue({
    levels: [level('low', 35, 9), level('normal', 50, 3), level('high', 60, 2)],
    k: 20, seeds: [1, 30], generated_at: '2026-11-06T17:00:00+00:00',
  })
})

test('the demand page shows all three levels, including the loss count', async () => {
  render(<DemandPage />)
  await screen.findByText('low')
  expect(screen.getByText('normal')).toBeInTheDocument()
  expect(screen.getByText('high')).toBeInTheDocument()
  expect(screen.getByText('9 of 30')).toBeInTheDocument()
})

test('the demand page says that a smaller deck raises percentages, not absolute profit', async () => {
  render(<DemandPage />)
  await screen.findByText('Tighter decks raise the percentage gain, not total profit. All results come from synthetic sailings.')
})

test('a missing table shows a message', async () => {
  vi.mocked(api.demandTable).mockRejectedValue(new ApiError(404, 'The demand table has not been generated.'))
  render(<DemandPage />)
  await screen.findByText(/not been generated/)
})
