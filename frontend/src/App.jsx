import { useState, useEffect, useRef } from 'react'

const API_BASE = 'http://localhost:8000/api'
const POLL_INTERVAL_MS = 2000  // Poll every 2 seconds

function App() {
  // Form state
  const [file, setFile] = useState(null)
  const [nlPrompt, setNlPrompt] = useState('')
  const [targetColumn, setTargetColumn] = useState('')
  const [replacementValue, setReplacementValue] = useState('')
  const [availableColumns, setAvailableColumns] = useState([])
  const [isLoadingColumns, setIsLoadingColumns] = useState(false)

  // Job state
  const [jobId, setJobId] = useState(null)
  const [jobStatus, setJobStatus] = useState(null)  // QUEUED, RUNNING, SUCCESS, FAILED, CANCELLED
  const [jobProgress, setJobProgress] = useState(0)
  const [jobError, setJobError] = useState(null)

  // UI state
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [formError, setFormError] = useState(null)

  // Ref to store the polling interval so we can clear it
  // useRef persists across renders without causing re-renders itself
  const pollingRef = useRef(null)

  // ---------------------------------------------------------------
  // POLLING LOGIC
  // Starts when we have a jobId, stops when the job reaches a
  // terminal state (SUCCESS, FAILED, CANCELLED).
  // ---------------------------------------------------------------
  useEffect(() => {
    if (!jobId) return

    // Start polling immediately, then repeat every POLL_INTERVAL_MS
    const poll = async () => {
      try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}/status/`)
        const data = await response.json()

        setJobStatus(data.status)
        setJobProgress(data.progress)

        if (data.error_message) {
          setJobError(data.error_message)
        }

        // Stop polling when the job reaches a terminal state
        const terminalStates = ['SUCCESS', 'FAILED', 'CANCELLED']
        if (terminalStates.includes(data.status)) {
          clearInterval(pollingRef.current)
        }

      } catch (err) {
        // Network error during polling — log it but keep polling.
        // A single failed poll shouldn't stop the whole process.
        console.error('Polling error:', err)
      }
    }

    // Poll immediately on mount, then on interval
    poll()
    pollingRef.current = setInterval(poll, POLL_INTERVAL_MS)

    // Cleanup: clear interval when component unmounts or jobId changes
    return () => clearInterval(pollingRef.current)
  }, [jobId])

  // ---------------------------------------------------------------
  // FILE SELECTION — reads columns immediately on file pick
  // ---------------------------------------------------------------
  const handleFileChange = async (e) => {
    const selectedFile = e.target.files[0]
    if (!selectedFile) return

    setFile(selectedFile)
    setAvailableColumns([])
    setTargetColumn('')
    setFormError(null)
    setIsLoadingColumns(true)

    const formData = new FormData()
    formData.append('file', selectedFile)

    try {
      const response = await fetch(`${API_BASE}/jobs/columns/`, {
        method: 'POST',
        body: formData,
      })
      const data = await response.json()

      if (!response.ok) throw new Error(data.error || 'Could not read columns')

      setAvailableColumns(data.columns)
      if (data.columns.length > 0) setTargetColumn(data.columns[0])

    } catch (err) {
      setFormError(`Could not read file: ${err.message}`)
      setFile(null)
    } finally {
      setIsLoadingColumns(false)
    }
  }

  // ---------------------------------------------------------------
  // FORM SUBMISSION
  // ---------------------------------------------------------------
  const handleSubmit = async () => {
    if (!file || !nlPrompt || !targetColumn || !replacementValue) {
      setFormError('Please fill in all fields and select a file.')
      return
    }

    setIsSubmitting(true)
    setFormError(null)
    setJobId(null)
    setJobStatus(null)
    setJobProgress(0)
    setJobError(null)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('nl_prompt', nlPrompt)
    formData.append('target_column', targetColumn)
    formData.append('replacement_value', replacementValue)

    try {
      const response = await fetch(`${API_BASE}/jobs/`, {
        method: 'POST',
        body: formData,
      })
      const data = await response.json()

      if (!response.ok) throw new Error(data.error || JSON.stringify(data))

      // Setting jobId triggers the useEffect polling loop above
      setJobId(data.id)

    } catch (err) {
      setFormError(err.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  // ---------------------------------------------------------------
  // CANCELLATION
  // ---------------------------------------------------------------
  const handleCancel = async () => {
    if (!jobId) return

    try {
      await fetch(`${API_BASE}/jobs/${jobId}/cancel/`, {
        method: 'POST',
      })
      // Polling loop will detect CANCELLED status on next poll
      // and stop itself automatically
    } catch (err) {
      console.error('Cancel error:', err)
    }
  }

  // ---------------------------------------------------------------
  // STATUS PANEL — shown while a job is running or complete
  // ---------------------------------------------------------------
  const renderJobStatus = () => {
    if (!jobId) return null

    const isTerminal = ['SUCCESS', 'FAILED', 'CANCELLED'].includes(jobStatus)
    const isRunning = ['QUEUED', 'RUNNING'].includes(jobStatus)

    return (
      <div style={{
        marginTop: '1.5rem',
        padding: '1rem',
        border: '1px solid #ccc',
        borderRadius: '8px'
      }}>
        <h3 style={{ marginTop: 0 }}>Job Status</h3>

        <p>
          <strong>ID:</strong> {jobId}<br />
          <strong>Status:</strong> {jobStatus || 'Loading...'}
        </p>

        {/* Progress bar */}
        <div style={{
          background: '#eee',
          borderRadius: '4px',
          height: '20px',
          overflow: 'hidden',
          marginBottom: '1rem'
        }}>
          <div style={{
            background: jobStatus === 'FAILED' ? '#e55' :
                        jobStatus === 'CANCELLED' ? '#aaa' : '#4a9',
            width: `${jobProgress}%`,
            height: '100%',
            transition: 'width 0.3s ease',
          }} />
        </div>
        <p style={{ textAlign: 'center', margin: '-0.5rem 0 1rem' }}>
          {jobProgress}%
        </p>

        {/* Cancel button — only shown while job is active */}
        {isRunning && (
          <button
            onClick={handleCancel}
            style={{
              padding: '0.5rem 1rem',
              background: '#e55',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Cancel Job
          </button>
        )}

        {/* Error message */}
        {jobError && (
          <div style={{ color: 'red', marginTop: '1rem' }}>
            Error: {jobError}
          </div>
        )}

        {/* Success message */}
        {jobStatus === 'SUCCESS' && (
          <div style={{ color: 'green', marginTop: '1rem' }}>
            ✅ Job completed successfully. Results will appear here in Step 4.
          </div>
        )}

        {/* Cancelled message */}
        {jobStatus === 'CANCELLED' && (
          <div style={{ color: '#888', marginTop: '1rem' }}>
            Job was cancelled.
          </div>
        )}
      </div>
    )
  }

  // ---------------------------------------------------------------
  // RENDER
  // ---------------------------------------------------------------
  return (
    <div style={{ padding: '2rem', maxWidth: '600px', margin: '0 auto' }}>
      <h1>RhombusAI — Data Processor</h1>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

        <div>
          <label>Upload CSV or Excel file</label><br />
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={handleFileChange}
          />
          {isLoadingColumns && (
            <p style={{ color: 'grey', fontSize: '0.9rem' }}>
              Reading columns...
            </p>
          )}
        </div>

        <div>
          <label>Describe the pattern (natural language)</label><br />
          <input
            type="text"
            placeholder="e.g. find email addresses"
            value={nlPrompt}
            onChange={(e) => setNlPrompt(e.target.value)}
            style={{ width: '100%', padding: '0.5rem' }}
          />
        </div>

        <div>
          <label>Target column</label><br />
          {availableColumns.length > 0 ? (
            <select
              value={targetColumn}
              onChange={(e) => setTargetColumn(e.target.value)}
              style={{ width: '100%', padding: '0.5rem' }}
            >
              {availableColumns.map((col) => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              placeholder="Upload a file to see available columns"
              disabled
              style={{ width: '100%', padding: '0.5rem', opacity: 0.5 }}
            />
          )}
        </div>

        <div>
          <label>Replacement value</label><br />
          <input
            type="text"
            placeholder="e.g. REDACTED"
            value={replacementValue}
            onChange={(e) => setReplacementValue(e.target.value)}
            style={{ width: '100%', padding: '0.5rem' }}
          />
        </div>

        <button
          onClick={handleSubmit}
          disabled={isSubmitting || availableColumns.length === 0}
          style={{ padding: '0.75rem', cursor: 'pointer' }}
        >
          {isSubmitting ? 'Submitting...' : 'Submit Job'}
        </button>

        {formError && (
          <div style={{ color: 'red', padding: '1rem', background: '#fee' }}>
            Error: {formError}
          </div>
        )}

      </div>

      {renderJobStatus()}

    </div>
  )
}

export default App