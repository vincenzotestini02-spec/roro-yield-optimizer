import type {
  Decision, DemandTable, ExportBody, GameState, LabDefaults, LabValues, RevealResult,
} from './types'

const POLL_MS = 1000

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

function detailText(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => item?.msg ?? String(item)).join('; ')
  return 'Something went wrong.'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'The server cannot be reached. It may be waking up: try again in a moment.')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, detailText(body.detail))
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

interface Job { job_id: string }
interface JobState<T> { status: string; progress: number; result: T | null; error: string | null }

export const api = {
  gameState: (seed: number, decisions: Decision[]) => post<GameState>('/api/game/state', { seed, decisions }),
  startVerdict: (seed: number, decisions: Decision[]) => post<Job>('/api/game/verdict', { seed, decisions }),
  reveal: (seed: number, decisions: Decision[]) => post<RevealResult>('/api/reveal', { seed, decisions }),
  bestPlan: (seed: number, decisions: Decision[], smartJob: string) =>
    post<Job>('/api/reveal/best', { seed, decisions, smart_job: smartJob }),
  labDefaults: () => request<LabDefaults>('/api/lab/defaults'),
  labPlans: (params: LabValues) => post<Job>('/api/lab/plans', params),
  labSmart: (params: LabValues) => post<Job>('/api/lab/smart', params),
  demandTable: () => request<DemandTable>('/api/demand-table'),
  cancelJob: (id: string) => request<void>(`/api/jobs/${id}`, { method: 'DELETE' }),
  exportPlan: async (body: ExportBody, format: 'pdf' | 'csv'): Promise<Blob> => {
    let response: Response
    try {
      response = await fetch(`/api/export/${format}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } catch {
      throw new ApiError(0, 'The server cannot be reached. Try again in a moment.')
    }
    if (!response.ok) {
      const detail = await response.json().then((b) => detailText(b.detail)).catch(() => 'The download failed.')
      throw new ApiError(response.status, detail)
    }
    return response.blob()
  },
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    }, { once: true })
  })
}

export async function pollJob<T>(id: string, onProgress: (p: number) => void, signal?: AbortSignal): Promise<T> {
  for (;;) {
    const job = await request<JobState<T>>(`/api/jobs/${id}`, { signal })
    onProgress(job.progress)
    if (job.status === 'done') return job.result as T
    if (job.status === 'failed') throw new ApiError(500, job.error ?? 'The calculation failed. Try again.')
    await sleep(POLL_MS, signal)
  }
}
