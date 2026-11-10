import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError, pollJob } from '../api'
import { DeckView } from '../components/DeckView'
import { DecisionTag } from '../components/DecisionTag'
import { StabilityView } from '../components/StabilityView'
import { clearGame, loadGame, saveGame } from '../storage'
import type { Booking, Decision, GameState, SavedGame, Verdict } from '../types'

function newGame(): SavedGame {
  return { seed: 1 + Math.floor(Math.random() * 10_000), decisions: [], verdicts: {} }
}

function message(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Something went wrong.'
}

function Gauge({ label, value, limit, unit }: { label: string; value: number; limit: number; unit: string }) {
  return (
    <div className="card">
      <span className="small muted">{label}</span>
      <strong>{value.toFixed(0)} / {limit.toFixed(0)} {unit}</strong>
      <div className="progress"><div style={{ width: `${limit > 0 ? Math.min(value / limit, 1) * 100 : 0}%` }} /></div>
    </div>
  )
}

function RequestCard({ b }: { b: Booking }) {
  return (
    <>
      <div className="row"><span className={`tag ${b.segment}`}>{b.segment.toUpperCase()}</span><strong>{b.customer}</strong></div>
      <h2 style={{ textTransform: 'capitalize' }}>{b.unit_label}{b.is_reefer ? ' (reefer)' : ''}</h2>
      <p className="muted">{b.length_m.toFixed(1)} m · {b.weight_t.toFixed(1)} t{b.is_reefer ? ' · needs a reefer plug' : ''}</p>
      <p>Rate <strong>€{b.rate_per_m.toFixed(0)}/m</strong> · Margin if loaded <strong>€{b.margin.toFixed(0)}</strong></p>
    </>
  )
}

export function GamePage() {
  const navigate = useNavigate()
  const [game, setGame] = useState<SavedGame>(() => loadGame() ?? newGame())
  const [state, setState] = useState<GameState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [manual, setManual] = useState(false)
  const [picking, setPicking] = useState(false)
  const [advisorOn, setAdvisorOn] = useState(false)
  const [verdictError, setVerdictError] = useState<string | null>(null)
  const [verdictTry, setVerdictTry] = useState(0)
  const [moveMode, setMoveMode] = useState(false)
  const [moving, setMoving] = useState<string | null>(null)
  const gameRef = useRef(game)

  const store = useCallback((next: SavedGame) => {
    gameRef.current = next
    setGame(next)
    saveGame(next)
  }, [])

  const load = useCallback(async (next: SavedGame) => {
    setBusy(true)
    setError(null)
    try {
      const fresh = await api.gameState(next.seed, next.decisions)
      store(next)
      setState(fresh)
      setPicking(false)
      if (fresh.finished) navigate('/reveal')
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }, [navigate, store])

  useEffect(() => { void load(gameRef.current) }, [load])

  const currentId = state?.current?.id
  const decisionCount = game.decisions.length  // a move keeps the request but changes the deck
  const verdict: Verdict | undefined = currentId === undefined ? undefined : game.verdicts[currentId]

  useEffect(() => {
    if (!advisorOn || currentId === undefined || gameRef.current.verdicts[currentId] !== undefined) return
    const abort = new AbortController()
    const { seed, decisions } = gameRef.current
    let openJob: string | null = null
    setVerdictError(null)
    api.startVerdict(seed, decisions)
      .then(({ job_id }) => {
        openJob = job_id
        if (abort.signal.aborted) {  // started after the player moved on
          void api.cancelJob(job_id).catch(() => {})
          throw new DOMException('Aborted', 'AbortError')
        }
        return pollJob<Verdict>(job_id, () => {}, abort.signal)
      })
      .then((result) => {
        openJob = null
        const now = gameRef.current
        store({ ...now, verdicts: { ...now.verdicts, [currentId]: result } })
      })
      .catch((e) => { if (!abort.signal.aborted) setVerdictError(message(e)) })
    return () => {
      abort.abort()
      // The player moved on: free the queue for the verdicts still to come.
      if (openJob !== null) void api.cancelJob(openJob).catch(() => {})
    }
  }, [advisorOn, currentId, decisionCount, verdictTry, store])

  function decide(...decisions: Decision[]) {
    const now = gameRef.current
    let verdicts = now.verdicts
    if (decisions.some((d) => d.action === 'move') && currentId !== undefined) {
      // The deck changes, so the verdict on the current request no longer holds.
      verdicts = Object.fromEntries(Object.entries(verdicts).filter(([id]) => id !== currentId))
    }
    void load({ ...now, verdicts, decisions: [...now.decisions, ...decisions] })
  }

  function moveTo(slot: string) {
    if (moving === null) return
    decide({ booking_id: moving, action: 'move', slot })
    setMoving(null)
    setMoveMode(false)
  }

  function applyMovesAndAccept() {
    if (!verdict || currentId === undefined) return
    const moves: Decision[] = verdict.moves.map((m) => ({ booking_id: m.booking_id, action: 'move', slot: m.to_slot }))
    decide(...moves, { booking_id: currentId, action: 'accept', slot: null })
  }

  function accept() {
    if (manual) setPicking(true)
    else decide({ booking_id: currentId as string, action: 'accept', slot: null })
  }

  function setPlacement(isManual: boolean) {
    setManual(isManual)
    setPicking(false)
  }

  function restart() {
    clearGame()
    void load(newGame())
  }

  if (state === null) {
    return error === null ? <p className="muted">Getting the sailing ready…</p> : (
      <div className="notice stack">
        <p>{error}</p>
        <div className="row">
          <button onClick={() => void load(gameRef.current)}>Try again</button>
          <button onClick={restart}>Start a new sailing</button>
        </div>
      </div>
    )
  }

  const { deck, current } = state
  const contractM = deck.placements.reduce((sum, p) => sum + (p.booking.segment === 'contract' ? p.booking.length_m : 0), 0)
  const margin = deck.placements.reduce((sum, p) => sum + p.booking.margin, 0)

  return (
    <>
      <div className="stack">
        <h1>You are the planner</h1>
        <p className="muted">
          {state.n_total} booking requests arrive one by one for {deck.vessel}, {deck.route}. Accept or reject each one.
          Contract cargo pays less but is guaranteed to key accounts. Spot cargo pays more but arrives later. The ship can't hold everything.
        </p>
        <div className="row">
          <div className="segmented">
            <button aria-pressed={!manual} onClick={() => setPlacement(false)}>App places them</button>
            <button aria-pressed={manual} onClick={() => setPlacement(true)}>I place them</button>
          </div>
          <button aria-pressed={advisorOn} onClick={() => setAdvisorOn(!advisorOn)}>{advisorOn ? 'Advisor off' : 'Advisor on'}</button>
          <button aria-pressed={moveMode} onClick={() => { setMoveMode(!moveMode); setMoving(null) }}>
            {moveMode ? 'Stop moving' : 'Move a unit'}
          </button>
          <button onClick={restart}>New sailing</button>
        </div>
        {state.moves > 0 && <p className="small">Moves: {state.moves} (−€{state.move_cost_eur.toFixed(0)})</p>}
      </div>
      <div className="grid-2">
        <section className="card" aria-label="Current request">
          <strong>Request {state.index + 1} of {state.n_total}</strong>
          <div className="progress"><div style={{ width: `${(state.index / state.n_total) * 100}%` }} /></div>
          {current && <RequestCard b={current} />}
          {advisorOn && verdict && (
            <div className="stack">
              <p><strong>Advisor:</strong> <DecisionTag verdict={verdict} /></p>
              <p>{verdict.text}</p>
              {verdict.moves.length > 0 && (
                <div><button className="primary" disabled={busy} onClick={applyMovesAndAccept}>Apply moves and accept</button></div>
              )}
            </div>
          )}
          {advisorOn && !verdict && !verdictError && <p className="muted small">The advisor is playing out possible futures…</p>}
          {advisorOn && verdictError && (
            <div className="notice stack">
              <p>{verdictError}</p>
              <div><button onClick={() => setVerdictTry(verdictTry + 1)}>Ask the advisor again</button></div>
            </div>
          )}
          {state.cannot_load_reason && <p className="notice">Can't load it: {state.cannot_load_reason}. Reject it to continue.</p>}
          {picking && <p className="notice">Pick a highlighted zone on the deck.</p>}
          <div className="row">
            {picking
              ? <button onClick={() => setPicking(false)}>Cancel</button>
              : <button className="primary" disabled={busy || state.cannot_load_reason !== null} onClick={accept}>Accept</button>}
            <button disabled={busy} onClick={() => decide({ booking_id: currentId as string, action: 'reject', slot: null })}>Reject</button>
          </div>
          {error && <p className="notice">{error}</p>}
          {state.floor_at_risk && (
            <p className="notice">Contract guarantee at risk: every missing contract metre costs a €{state.shortfall_penalty_per_m.toFixed(0)}/m penalty.</p>
          )}
        </section>
        <div className="stack">
          <div className="grid-3">
            <Gauge label="Lane-metres used" value={deck.used_m} limit={deck.capacity_m} unit="m" />
            <Gauge label="Deadweight" value={deck.weight_t} limit={deck.max_dwt_t} unit="t" />
            <Gauge label="Reefer plugs" value={deck.plugs_used} limit={deck.reefer_plugs} unit="" />
          </div>
          <div className="card">
            <DeckView deck={deck} highlightSlots={picking ? state.feasible_slots : []}
              onSlotClick={(slot) => decide({ booking_id: currentId as string, action: 'accept', slot })}
              onUnitClick={moveMode ? setMoving : undefined} selectedUnit={moving} />
            {moveMode && (
              <div className="stack">
                <p className="small">{moving === null ? 'Click a unit on the deck to move it. Each move costs €80.' : `Move ${moving} to:`}</p>
                {moving !== null && (
                  <div className="row">
                    {deck.lanes.flatMap((lane) => Array.from({ length: deck.zones }, (_, z) => `${lane.id}-Z${z}`)).map((slot) => (
                      <button key={slot} aria-label={`Zone ${slot}`} disabled={busy} onClick={() => moveTo(slot)}>{slot}</button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {picking && (
              <div className="row">
                {state.feasible_slots.map((slot) => (
                  <button key={slot} aria-label={`Zone ${slot}`}
                    onClick={() => decide({ booking_id: currentId as string, action: 'accept', slot })}>{slot}</button>
                ))}
              </div>
            )}
            <p className="small muted">
              Contract metres {contractM.toFixed(0)} / {state.contract_floor_m.toFixed(0)} guaranteed · Your margin so far €{margin.toFixed(0)}
            </p>
          </div>
          <div className="card"><StabilityView deck={deck} /></div>
        </div>
      </div>
    </>
  )
}
