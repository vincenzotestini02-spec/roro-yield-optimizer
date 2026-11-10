import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError, pollJob } from '../api'
import { clearGame, saveGame } from '../storage'
import { booking, gameState, verdict } from '../test/fixtures'
import { GamePage } from './GamePage'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { gameState: vi.fn(), startVerdict: vi.fn(), cancelJob: vi.fn() },
  pollJob: vi.fn(),
}))
const gameMock = vi.mocked(api.gameState)

function show() {
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<GamePage />} />
        <Route path="/reveal" element={<p>reveal page</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  clearGame()
  gameMock.mockResolvedValue(gameState())
  vi.mocked(api.startVerdict).mockResolvedValue({ job_id: 'j1' })
  vi.mocked(api.cancelJob).mockResolvedValue(undefined)
  vi.mocked(pollJob).mockResolvedValue(verdict())
})

test('accept sends the decision and shows the next request', async () => {
  show()
  await screen.findByText(/Request 1 of 60/)
  gameMock.mockResolvedValue(gameState({ index: 1, current: booking('B002') }))
  await userEvent.click(screen.getByRole('button', { name: 'Accept' }))
  await screen.findByText(/Request 2 of 60/)
  expect(gameMock.mock.lastCall?.[1]).toEqual([{ booking_id: 'B001', action: 'accept', slot: null }])
})

test('manual mode waits for a slot click before deciding', async () => {
  show()
  await screen.findByText(/Request 1 of 60/)
  await userEvent.click(screen.getByRole('button', { name: /I place them/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Accept' }))
  expect(gameMock).toHaveBeenCalledTimes(1)
  await userEvent.click(screen.getByRole('button', { name: 'Load in L2-Z0' }))
  await waitFor(() => expect(gameMock.mock.lastCall?.[1]).toEqual(
    [{ booking_id: 'B001', action: 'accept', slot: 'L2-Z0' }]))
})

test('zone buttons offer a larger target for manual placement', async () => {
  show()
  await screen.findByText(/Request 1 of 60/)
  await userEvent.click(screen.getByRole('button', { name: /I place them/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Accept' }))
  await userEvent.click(screen.getByRole('button', { name: 'Zone L2-Z0' }))
  await waitFor(() => expect(gameMock.mock.lastCall?.[1]).toEqual(
    [{ booking_id: 'B001', action: 'accept', slot: 'L2-Z0' }]))
})

test('only feasible slots are clickable in manual mode', async () => {
  show()
  await screen.findByText(/Request 1 of 60/)
  await userEvent.click(screen.getByRole('button', { name: /I place them/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Accept' }))
  expect(screen.getAllByRole('button', { name: /^Load in/ })).toHaveLength(2)
})

test('a request that cannot load explains why and leaves Reject available', async () => {
  gameMock.mockResolvedValue(gameState({ cannot_load_reason: 'not enough deck space', feasible_slots: [], best_slot: null }))
  show()
  await screen.findByText(/not enough deck space/)
  expect(screen.getByRole('button', { name: 'Accept' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Reject' })).toBeEnabled()
})

test('a reloaded page resumes the saved game', async () => {
  const saved = [{ booking_id: 'B001', action: 'reject' as const, slot: null }]
  saveGame({ seed: 77, decisions: saved, verdicts: {} })
  show()
  await waitFor(() => expect(gameMock).toHaveBeenCalledWith(77, saved))
})

test('advisor text appears when the verdict job finishes', async () => {
  show()
  await screen.findByText(/Request 1 of 60/)
  await userEvent.click(screen.getByRole('button', { name: 'Advisor on' }))
  await screen.findByText(/pays off in 15 of 20/)
})

test('the advisor stays off until asked', async () => {
  show()
  await screen.findByText(/Request 1 of 60/)
  expect(api.startVerdict).not.toHaveBeenCalled()
})

test('a lost verdict job shows a retry button, and the game can continue', async () => {
  vi.mocked(pollJob).mockRejectedValueOnce(new ApiError(404, 'This calculation is no longer on the server.'))
  show()
  await screen.findByText(/Request 1 of 60/)
  await userEvent.click(screen.getByRole('button', { name: 'Advisor on' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Ask the advisor again' }))
  await screen.findByText(/pays off in 15 of 20/)
  expect(screen.getByRole('button', { name: 'Reject' })).toBeEnabled()
})

test('moving on cancels a verdict still in the queue', async () => {
  vi.mocked(pollJob).mockImplementation(() => new Promise(() => {}))
  show()
  await screen.findByText(/Request 1 of 60/)
  await userEvent.click(screen.getByRole('button', { name: 'Advisor on' }))
  await waitFor(() => expect(pollJob).toHaveBeenCalled())
  gameMock.mockResolvedValue(gameState({ index: 1, current: booking('B002') }))
  await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
  await waitFor(() => expect(api.cancelJob).toHaveBeenCalledWith('j1'))
})

test('a verdict that starts after the player moved on is cancelled', async () => {
  const releases: ((v: { job_id: string }) => void)[] = []
  vi.mocked(api.startVerdict).mockImplementation(() => new Promise((r) => { releases.push(r) }))
  show()
  await screen.findByText(/Request 1 of 60/)
  await userEvent.click(screen.getByRole('button', { name: 'Advisor on' }))
  gameMock.mockResolvedValue(gameState({ index: 1, current: booking('B002') }))
  await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
  await screen.findByText(/Request 2 of 60/)
  releases[0]({ job_id: 'late' })  // the verdict for the request already left
  await waitFor(() => expect(api.cancelJob).toHaveBeenCalledWith('late'))
})

test('a saved game the server rejects can be replaced by a new sailing', async () => {
  saveGame({ seed: 77, decisions: [{ booking_id: 'B001', action: 'accept', slot: 'L9-Z0' }], verdicts: {} })
  gameMock.mockRejectedValueOnce(new ApiError(422, 'L9-Z0 is not a deck zone.'))
  show()
  await userEvent.click(await screen.findByRole('button', { name: 'Start a new sailing' }))
  await screen.findByText(/Request 1 of 60/)
  expect(gameMock.mock.lastCall?.[1]).toEqual([])
})

test('a contract floor warning is shown', async () => {
  gameMock.mockResolvedValue(gameState({ floor_at_risk: true }))
  show()
  await screen.findByText(/contract guarantee at risk/i)
})

test('the last decision navigates to the reveal', async () => {
  show()
  await screen.findByText(/Request 1 of 60/)
  gameMock.mockResolvedValue(gameState({ finished: true, current: null, index: 60 }))
  await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
  await screen.findByText('reveal page')
})

test('a server error can be retried', async () => {
  gameMock.mockRejectedValueOnce(new ApiError(0, 'The server cannot be reached.'))
  show()
  await userEvent.click(await screen.findByRole('button', { name: 'Try again' }))
  await screen.findByText(/Request 1 of 60/)
})

const loadedDeck = () => gameState({
  deck: { ...gameState().deck, placements: [{ booking_id: 'B000', slot: 'L1-Z0', booking: booking('B000') }] },
})

test('a unit can be moved on the deck and the move is saved', async () => {
  gameMock.mockResolvedValue(loadedDeck())
  show()
  await screen.findByText(/Request 1 of 60/)
  await userEvent.click(screen.getByRole('button', { name: 'Move a unit' }))
  await userEvent.click(screen.getByRole('button', { name: 'Unit B000' }))
  await userEvent.click(screen.getByRole('button', { name: 'Zone L2-Z0' }))
  await waitFor(() => expect(gameMock.mock.lastCall?.[1]).toEqual([{ booking_id: 'B000', action: 'move', slot: 'L2-Z0' }]))
})

test('a refused move shows the reason and changes nothing', async () => {
  gameMock.mockResolvedValue(loadedDeck())
  show()
  await screen.findByText(/Request 1 of 60/)
  gameMock.mockRejectedValueOnce(new ApiError(422, 'B000 cannot move: it does not fit there (space or stability).'))
  await userEvent.click(screen.getByRole('button', { name: 'Move a unit' }))
  await userEvent.click(screen.getByRole('button', { name: 'Unit B000' }))
  await userEvent.click(screen.getByRole('button', { name: 'Zone L2-Z0' }))
  await screen.findByText(/does not fit there/)
  expect(screen.getByText(/Request 1 of 60/)).toBeInTheDocument()
})

test('the move counter shows the cost', async () => {
  gameMock.mockResolvedValue(gameState({ moves: 2, move_cost_eur: 160 }))
  show()
  await screen.findByText('Moves: 2 (−€160)')
})

test('your call is shown with the share and the range', async () => {
  vi.mocked(pollJob).mockResolvedValue(verdict({
    decision: 'your_call', n_pays_off: 11, pays_off_share: 0.55, gain_low: -300, gain_high: 380,
    text: 'Your call — pays off in 11 of 20 futures, expected gain +€20 (range −€300 to +€380)',
  }))
  show()
  await screen.findByText(/Request 1 of 60/)
  await userEvent.click(screen.getByRole('button', { name: 'Advisor on' }))
  await screen.findByText('Your call')
  expect(screen.getByText(/range −€300 to \+€380/)).toBeInTheDocument()
})

test('apply moves and accept sends the moves first, then the accept', async () => {
  vi.mocked(pollJob).mockResolvedValue(verdict({
    moves: [{ booking_id: 'B000', from_slot: 'L1-Z0', to_slot: 'L2-Z0' }],
    text: 'Move B000 from L1-Z0 to L2-Z0, then: Accept — pays off in 15 of 20 futures',
  }))
  show()
  await screen.findByText(/Request 1 of 60/)
  await userEvent.click(screen.getByRole('button', { name: 'Advisor on' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Apply moves and accept' }))
  await waitFor(() => expect(gameMock.mock.lastCall?.[1]).toEqual([
    { booking_id: 'B000', action: 'move', slot: 'L2-Z0' },
    { booking_id: 'B001', action: 'accept', slot: null },
  ]))
})
