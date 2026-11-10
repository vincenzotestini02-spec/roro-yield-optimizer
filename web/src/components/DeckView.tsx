import type React from 'react'
import type { Deck } from '../types'

const WIDTH = 1000
const LEFT = 44
const LANE_HEIGHT = 34
const LANE_GAP = 6
const TOP = 26

interface Props {
  deck: Deck
  highlightSlots?: string[]
  onSlotClick?: (slot: string) => void
  onUnitClick?: (bookingId: string) => void
  selectedUnit?: string | null
}

function parseSlot(slot: string): { laneId: string; zone: number } {
  const at = slot.lastIndexOf('-Z')
  return { laneId: slot.slice(0, at), zone: Number(slot.slice(at + 2)) }
}

export function DeckView({ deck, highlightSlots = [], onSlotClick, onUnitClick, selectedUnit = null }: Props) {
  const lanes = [...deck.lanes].sort((a, b) => a.y_m - b.y_m)
  const longest = Math.max(1, ...lanes.map((lane) => lane.length_m))
  const scale = (WIDTH - LEFT - 8) / longest
  const yOf = new Map(lanes.map((lane, i) => [lane.id, TOP + i * (LANE_HEIGHT + LANE_GAP)]))
  const laneOf = new Map(lanes.map((lane) => [lane.id, lane]))
  const height = TOP + lanes.length * (LANE_HEIGHT + LANE_GAP)
  const used = new Map<string, number>()

  return (
    <svg className="deck" viewBox={`0 0 ${WIDTH} ${height}`} role="img"
      aria-label={`Deck plan: ${deck.placements.length} units loaded`}>
      <text x={LEFT} y={18}>Stern</text>
      <text x={WIDTH - 8} y={18} textAnchor="end">Bow</text>
      {lanes.map((lane) => {
        const y = yOf.get(lane.id) as number
        const zoneWidth = (lane.length_m / deck.zones) * scale
        return (
          <g key={lane.id}>
            <text x={0} y={y + LANE_HEIGHT / 2 + 6}>{lane.id}</text>
            <rect className="lane" x={LEFT} y={y} width={lane.length_m * scale} height={LANE_HEIGHT} rx={3} />
            {Array.from({ length: deck.zones - 1 }, (_, i) => (
              <line key={i} className="zone-line" x1={LEFT + (i + 1) * zoneWidth} x2={LEFT + (i + 1) * zoneWidth}
                y1={y} y2={y + LANE_HEIGHT} />
            ))}
          </g>
        )
      })}
      {deck.placements.map(({ booking_id, slot, booking }) => {
        const { laneId, zone } = parseSlot(slot)
        const lane = laneOf.get(laneId)
        if (lane === undefined) return null
        const offset = used.get(slot) ?? 0
        used.set(slot, offset + booking.length_m + 0.5)
        const x = LEFT + (zone * (lane.length_m / deck.zones) + offset) * scale
        return (
          <rect key={booking_id} className={`unit ${booking.segment}${selectedUnit === booking_id ? ' selected' : ''}`}
            x={x} y={(yOf.get(laneId) as number) + 4} width={booking.length_m * scale} height={LANE_HEIGHT - 8} rx={2}
            {...(onUnitClick ? {
              role: 'button', tabIndex: 0, 'aria-label': `Unit ${booking_id}`, style: { cursor: 'pointer' },
              onClick: () => onUnitClick(booking_id),
              onKeyDown: (e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') onUnitClick(booking_id) },
            } : {})}>
            <title>{`${booking.id} · ${booking.customer} · ${booking.unit_label} · ${booking.length_m} m · ${booking.weight_t} t`}</title>
          </rect>
        )
      })}
      {highlightSlots.map((slot) => {
        const { laneId, zone } = parseSlot(slot)
        const lane = laneOf.get(laneId)
        if (lane === undefined) return null
        const zoneWidth = (lane.length_m / deck.zones) * scale
        return (
          <rect key={slot} className="pick" role="button" tabIndex={0} aria-label={`Load in ${slot}`}
            x={LEFT + zone * zoneWidth} y={yOf.get(laneId)} width={zoneWidth} height={LANE_HEIGHT}
            onClick={() => onSlotClick?.(slot)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onSlotClick?.(slot) }} />
        )
      })}
    </svg>
  )
}
