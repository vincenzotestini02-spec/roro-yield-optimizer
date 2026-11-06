import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError, pollJob } from '../api'
import { planResult } from '../test/fixtures'
import { LabPage } from './LabPage'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { labDefaults: vi.fn(), labPlans: vi.fn(), labSmart: vi.fn(), cancelJob: vi.fn(), manifestCsv: vi.fn() },
  pollJob: vi.fn(),
}))

const plans = { fcfs: planResult('FCFS', 2000), optimal: planResult('Optimizer', 4000) }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.labDefaults).mockResolvedValue({
    values: { n_requests: 60, n_lanes: 5, seed: 42, contract_share: 0.45 },
    limits: { n_requests: [30, 200], n_lanes: [1, 16], seed: [1, 10000], contract_share: [0, 0.9] },
    advisor_k: 20,
  })
  vi.mocked(api.labPlans).mockResolvedValue({ job_id: 'p1' })
  vi.mocked(api.labSmart).mockResolvedValue({ job_id: 's1' })
  vi.mocked(api.cancelJob).mockResolvedValue(undefined)
  vi.mocked(pollJob).mockResolvedValue(plans)
})

test('the lab sends edited values and renders both plans', async () => {
  render(<LabPage />)
  const lanes = await screen.findByLabelText(/Lanes/)
  fireEvent.change(lanes, { target: { value: '4' } })
  await userEvent.click(screen.getByRole('button', { name: 'Compare plans' }))
  await waitFor(() => expect(api.labPlans).toHaveBeenLastCalledWith(expect.objectContaining({ n_lanes: 4 })))
  expect(await screen.findByRole('columnheader', { name: 'Optimizer' })).toBeInTheDocument()
  expect(screen.getByText('+100.0%')).toBeInTheDocument()
})

test('the lab shows the busy message on a 429', async () => {
  vi.mocked(api.labPlans).mockRejectedValue(new ApiError(429, 'The server is busy. Try again in a moment.'))
  render(<LabPage />)
  await screen.findByText(/server is busy/)
})

test('the lab cancels a running smart plan', async () => {
  render(<LabPage />)
  await screen.findByRole('columnheader', { name: 'Optimizer' })
  vi.mocked(pollJob).mockImplementation(() => new Promise(() => {}))
  await userEvent.click(screen.getByRole('button', { name: /Run the smart planner/ }))
  await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
  expect(api.cancelJob).toHaveBeenCalledWith('s1')
  await screen.findByRole('button', { name: /Run the smart planner/ })
})

test('the smart plan joins the comparison', async () => {
  render(<LabPage />)
  await screen.findByRole('columnheader', { name: 'Optimizer' })
  vi.mocked(pollJob).mockResolvedValue({ smart: planResult('Smart planner', 3000), best: planResult('Optimizer', 4100) })
  await userEvent.click(screen.getByRole('button', { name: /Run the smart planner/ }))
  await screen.findByRole('columnheader', { name: 'Smart planner' })
})
