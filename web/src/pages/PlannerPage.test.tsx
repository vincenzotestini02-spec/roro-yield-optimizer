import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import App from '../App'
import { api, pollJob } from '../api'
import { clearPlanner, savePlanner } from '../planner'
import { deck, kpis } from '../test/fixtures'
import type { PlannerBookingIn, PlannerPlan } from '../types'
import { PlannerPage } from './PlannerPage'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: {
    labDefaults: vi.fn(), importBookings: vi.fn(), plannerPlan: vi.fn(), plannerMove: vi.fn(),
    plannerAdvise: vi.fn(), exportPlan: vi.fn(), gameState: vi.fn(),
  },
  pollJob: vi.fn(),
}))
vi.mock('../download', () => ({ downloadBlob: vi.fn() }))

const booking = (id: string, over: Partial<PlannerBookingIn> = {}): PlannerBookingIn => ({
  booking_id: id, customer: 'Nordfreight', unit_type: 'semi_trailer', length_m: 13.6, weight_t: 22,
  discharge_port: 'Immingham', segment: 'contract', is_reefer: false, rate_per_m: 50, reefer_fee: null,
  height_m: null, axle_count: null, on_board: false, ...over,
})

const planResult = (over: Partial<PlannerPlan> = {}): PlannerPlan => ({
  placements: { B1: 'L1-Z0', B2: 'L2-Z0' }, excluded: [], moved: [], deck: deck(), kpis: kpis('Planner', 1000),
  revenue_known: true, ...over,
})

function file() {
  return new File(['x'], 'bookings.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}

beforeEach(() => {
  vi.clearAllMocks()
  clearPlanner()
  localStorage.clear()
  vi.mocked(api.labDefaults).mockResolvedValue({
    values: { n_lanes: 5, lane_length_m: 120, broken_stowage_pct: 0 },
    limits: { n_lanes: [1, 16], lane_length_m: [70, 250], broken_stowage_pct: [0, 0.3] },
    advisor_k: 20,
    presets: {
      demo: { label: 'Demo ferry, 600 lane-m', values: { n_lanes: 5, lane_length_m: 120 } },
      shortsea: { label: 'Short-sea RoRo, about 2,500 lane-m', values: { n_lanes: 16, lane_length_m: 156 } },
    },
    note: 'Typical rounded figures, not a named ship.',
  })
  vi.mocked(api.importBookings).mockResolvedValue({ bookings: [booking('B1'), booking('B2')], errors: [], warnings: [] })
  vi.mocked(api.plannerPlan).mockResolvedValue({ job_id: 'p1' })
  vi.mocked(pollJob).mockResolvedValue(planResult())
})

test('the planner is the home page and the game moved to /game', async () => {
  window.history.pushState({}, '', '/')
  render(<App />)
  expect(await screen.findByRole('heading', { name: 'Planner' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Game' })).toHaveAttribute('href', '/game')
})

test('an uploaded file with errors shows every row error and no plan', async () => {
  vi.mocked(api.importBookings).mockResolvedValue({
    bookings: [], warnings: [],
    errors: [{ row: 3, column: 'length_m', message: "'x' is not a number" }, { row: 5, column: 'unit_type', message: 'unknown' }],
  })
  render(<MemoryRouter><PlannerPage /></MemoryRouter>)
  await userEvent.upload(await screen.findByLabelText(/Upload bookings/), file())
  await screen.findByText("'x' is not a number")
  expect(screen.getByText('unknown')).toBeInTheDocument()
  expect(api.plannerPlan).not.toHaveBeenCalled()
})

test('a valid file shows the plan with the deck', async () => {
  render(<MemoryRouter><PlannerPage /></MemoryRouter>)
  await userEvent.upload(await screen.findByLabelText(/Upload bookings/), file())
  await screen.findByRole('img', { name: /Deck plan/ })
  expect(api.plannerPlan).toHaveBeenCalledWith(expect.objectContaining({ bookings: [booking('B1'), booking('B2')] }))
})

test('excluded bookings are listed with their reasons', async () => {
  vi.mocked(pollJob).mockResolvedValue(planResult({ excluded: [{ booking_id: 'B2', reason: 'no lane has enough space left' }] }))
  render(<MemoryRouter><PlannerPage /></MemoryRouter>)
  await userEvent.upload(await screen.findByLabelText(/Upload bookings/), file())
  await screen.findByText(/no lane has enough space left/)
  expect(screen.getByText(/never dropped silently/)).toBeInTheDocument()
})

test('revenue shows n/a when prices are missing', async () => {
  vi.mocked(pollJob).mockResolvedValue(planResult({ revenue_known: false }))
  render(<MemoryRouter><PlannerPage /></MemoryRouter>)
  await userEvent.upload(await screen.findByLabelText(/Upload bookings/), file())
  await screen.findByText('Revenue')
  expect(screen.getByTestId('revenue')).toHaveTextContent('n/a')
})

test('a damaged saved session starts empty with a notice', async () => {
  localStorage.setItem('roro-planner', '{"vessel": 3}')
  render(<MemoryRouter><PlannerPage /></MemoryRouter>)
  await screen.findByText(/saved planner session could not be read/)
  expect(api.plannerPlan).not.toHaveBeenCalled()
})

test('changing the vessel replans', async () => {
  render(<MemoryRouter><PlannerPage /></MemoryRouter>)
  await userEvent.upload(await screen.findByLabelText(/Upload bookings/), file())
  await screen.findByRole('img', { name: /Deck plan/ })
  await userEvent.selectOptions(screen.getByLabelText('Vessel'), 'shortsea')
  await waitFor(() => expect(api.plannerPlan).toHaveBeenLastCalledWith(
    expect.objectContaining({ vessel: expect.objectContaining({ preset: 'shortsea', n_lanes: 16 }) })))
})

test('a saved session comes back after a reload', async () => {
  savePlanner({
    vessel: { preset: 'demo', broken_stowage_pct: 0.15, n_lanes: 5, lane_length_m: 120 }, bookings: [booking('B1')],
    placements: { B1: 'L1-Z0' }, demand: { level: 'normal', contract_share: 0.45, spot_rate_multiplier: 1, window_days: 14, hours_to_departure: 72 },
    log: [],
  })
  render(<MemoryRouter><PlannerPage /></MemoryRouter>)
  await waitFor(() => expect(api.plannerPlan).toHaveBeenCalledWith(expect.objectContaining({ placements: { B1: 'L1-Z0' } })))
})
