export function JobProgress({ label, progress, onCancel }: { label: string; progress: number; onCancel?: () => void }) {
  return (
    <div className="stack">
      <div className="row small" style={{ justifyContent: 'space-between' }}>
        <span>{label}</span><span>{Math.round(progress * 100)}%</span>
      </div>
      <div className="progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}>
        <div style={{ width: `${progress * 100}%` }} />
      </div>
      {onCancel && <div><button onClick={onCancel}>Cancel</button></div>}
    </div>
  )
}
