import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError, pollJob } from '../api'
import { saveGame } from '../storage'
import { booking, gameState, verdict } from '../test/fixtures'
import { GamePage } from './GamePage'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { gameState: vi.fn(), startVerdict: vi.fn() },
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
  localStorage.clear()
  gameMock.mockResolvedValue(gameState())
  vi.mocked(api.startVerdict).mockResolvedValue({ job_id: 'j1' })
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
