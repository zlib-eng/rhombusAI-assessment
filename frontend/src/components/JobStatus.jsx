// ─────────────────────────────────────────────────────────────
// JobStatus — the status strip. State is communicated three
// redundant ways at once (left border color, label color, label
// text) so it's glanceable and colorblind-safe. The progress bar
// is integrated into the strip rather than floating separately.
// ─────────────────────────────────────────────────────────────

const STATUS_LABELS = {
  QUEUED: 'QUEUED',
  RUNNING: 'RUNNING',
  SUCCESS: 'COMPLETE',
  FAILED: 'FAILED',
  CANCELLED: 'CANCELLED',
}

export default function JobStatus({ jobId, status, progress, jobError, onCancel }) {
  if (!jobId) return null

  const statusClass = status ? `status-strip--${status.toLowerCase()}` : ''
  const isRunning = ['QUEUED', 'RUNNING'].includes(status)

  return (
    <div className="job-panel">
      <div className={`status-strip ${statusClass}`} role="status" aria-live="polite">
        <span className="status-strip__label">
          {STATUS_LABELS[status] || 'STARTING'}
        </span>
        <div className="status-strip__bar" aria-hidden="true">
          <div
            className="status-strip__bar-fill"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="status-strip__pct">{progress}%</span>
      </div>

      <div className="job-panel__body">
        <p className="job-panel__meta">job {jobId}</p>

        {isRunning && (
          <button className="btn btn--danger" onClick={onCancel}>
            Cancel job
          </button>
        )}

        {jobError && (
          <p className="job-panel__error" role="alert">{jobError}</p>
        )}

        {status === 'CANCELLED' && (
          <p className="job-panel__note">
            This job was cancelled. The source file was not modified.
          </p>
        )}
      </div>
    </div>
  )
}
