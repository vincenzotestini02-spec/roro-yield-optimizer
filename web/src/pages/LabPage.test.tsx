import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError, pollJob } from '../api'
import { planResult } from '../test/fixtures'
import { LabPage } from './LabPage'
import { downloadBlob } from '../download'

vi.mock('../download', () => ({ downloadBlob: vi.fn() }))

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { labDefaults: vi.fn(), labPlans: vi.fn(), labSmart: vi.fn(), cancelJob: vi.fn(), exportPlan: vi.fn() },
  pollJob: vi.fn(),
}))

const plans = { fcfs: planResult('FCFS', 2000), optimal: planResult('Optimizer', 4000), smart_may_be_slow: false }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.labDefaults).mockResolvedValue({
    values: { n_requests: 60, n_lanes: 5, seed: 42, contract_share: 0.45, broken_stowage_pct: 0 },
    limits: { n_requests: [30, 200], n_lanes: [1, 16], seed: [1, 10000], contract_share: [0, 0.9], broken_stowage_pct: [0, 0.3] },
    advisor_k: 20,
    presets: {
      demo: { label: 'Demo ferry, 600 lane-m', values: { n_lanes: 5, n_requests: 60 } },
      shortsea: { label: 'Short-sea RoRo, about 2,500 lane-m', values: { n_lanes: 16, n_requests: 190 } },
    },
    note: 'Typical rounded figures, not a named ship.',
  })
  vi.mocked(api.exportPlan).mockResolvedValue(new Blob(['x']))
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

test('comparing new settings stops the smart run of the old ones', async () => {
  render(<LabPage />)
  await screen.findByRole('columnheader', { name: 'Optimizer' })
  vi.mocked(pollJob).mockImplementationOnce(() => new Promise(() => {}))
  await userEvent.click(screen.getByRole('button', { name: /Run the smart planner/ }))
  await screen.findByRole('button', { name: 'Cancel' })
  vi.mocked(pollJob).mockResolvedValue(plans)
  await userEvent.click(screen.getByRole('button', { name: 'Compare plans' }))
  await waitFor(() => expect(api.cancelJob).toHaveBeenCalledWith('s1'))
})

test('choosing a vessel preset loads its values and compares', async () => {
  render(<LabPage />)
  await screen.findByRole('columnheader', { name: 'Optimizer' })
  await userEvent.selectOptions(screen.getByLabelText('Vessel'), 'shortsea')
  await waitFor(() => expect(api.labPlans).toHaveBeenLastCalledWith(expect.objectContaining({ n_lanes: 16, n_requests: 190 })))
})

test('the preset note is shown', async () => {
  render(<LabPage />)
  await screen.findByText('Typical rounded figures, not a named ship.')
})

test('lost space has its own slider in percent', async () => {
  render(<LabPage />)
  const slider = await screen.findByLabelText(/Lost space/)
  fireEvent.change(slider, { target: { value: '0.15' } })
  expect(screen.getByText('15%')).toBeInTheDocument()
})

test('a slow smart run asks for confirmation first', async () => {
  vi.mocked(pollJob).mockResolvedValue({ ...plans, smart_may_be_slow: true })
  render(<LabPage />)
  await screen.findByRole('columnheader', { name: 'Optimizer' })
  await userEvent.click(screen.getByRole('button', { name: /Run the smart planner/ }))
  expect(screen.getByText(/several minutes/)).toBeInTheDocument()
  expect(api.labSmart).not.toHaveBeenCalled()
  vi.mocked(pollJob).mockImplementation(() => new Promise(() => {}))
  await userEvent.click(screen.getByRole('button', { name: 'Run anyway' }))
  await waitFor(() => expect(api.labSmart).toHaveBeenCalled())
})

test('PDF and CSV download the best plan', async () => {
  render(<LabPage />)
  await screen.findByRole('columnheader', { name: 'Optimizer' })
  await userEvent.click(screen.getByRole('button', { name: 'Download PDF' }))
  await userEvent.click(screen.getByRole('button', { name: 'Download CSV' }))
  expect(api.exportPlan).toHaveBeenCalledWith(expect.objectContaining({ source: 'lab', plan_key: 'optimal' }), 'pdf')
  expect(api.exportPlan).toHaveBeenCalledWith(expect.objectContaining({ source: 'lab', plan_key: 'optimal' }), 'csv')
  await waitFor(() => expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'roro-plan-optimal.pdf'))
})

test('a 409 on export shows the reason', async () => {
  vi.mocked(api.exportPlan).mockRejectedValue(new ApiError(409, 'This plan is not ready yet. Wait for it, then download.'))
  render(<LabPage />)
  await screen.findByRole('columnheader', { name: 'Optimizer' })
  await userEvent.click(screen.getByRole('button', { name: 'Download PDF' }))
  await screen.findByText(/not ready yet/)
})

test('the lab applies values from #p= and compares', async () => {
  window.location.hash = '#p=' + btoa(JSON.stringify({ n_lanes: 3, nonsense: 9 })).replace(/=+$/, '')
  render(<LabPage />)
  await waitFor(() => expect(api.labPlans).toHaveBeenCalledWith(expect.objectContaining({ n_lanes: 3 })))
  window.location.hash = ''
})

test('a damaged lab link falls back to the defaults with a message', async () => {
  window.location.hash = '#p=@@'
  render(<LabPage />)
  await screen.findByText(/damaged or incomplete/)
  expect(api.labPlans).toHaveBeenCalledWith(expect.objectContaining({ n_lanes: 5 }))
  window.location.hash = ''
})
