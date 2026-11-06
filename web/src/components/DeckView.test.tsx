import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import { booking, deck } from '../test/fixtures'
import { DeckView } from './DeckView'

const loaded = deck({
  placements: [
    { booking_id: 'B1', slot: 'L1-Z0', booking: booking('B1', { segment: 'contract', customer: 'Nordfreight' }) },
    { booking_id: 'B2', slot: 'L2-Z3', booking: booking('B2') },
  ],
})

test('draws one lane per lane and four zones in each', () => {
  const { container } = render(<DeckView deck={loaded} />)
  expect(container.querySelectorAll('.lane')).toHaveLength(2)
  expect(container.querySelectorAll('.zone-line')).toHaveLength(2 * 3)
})

test('units use their segment colour class and show details', () => {
  const { container } = render(<DeckView deck={loaded} />)
  expect(container.querySelector('.unit.contract title')?.textContent).toContain('Nordfreight')
  expect(container.querySelector('.unit.spot title')?.textContent).toContain('B2')
})

test('only highlighted slots can be clicked', async () => {
  const onSlotClick = vi.fn()
  render(<DeckView deck={loaded} highlightSlots={['L1-Z1']} onSlotClick={onSlotClick} />)
  const picks = screen.getAllByRole('button')
  expect(picks).toHaveLength(1)
  await userEvent.click(picks[0])
  expect(onSlotClick).toHaveBeenCalledWith('L1-Z1')
})
