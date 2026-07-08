import { useState, useEffect, useRef } from 'react'

const API_BASE = 'http://3.106.244.151:8000/api'
const POLL_INTERVAL_MS = 2000

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
  const [jobStatus, setJobStatus] = useState(null)
  const [jobProgress, setJobProgress] = useState(0)
  const [jobError, setJobError] = useState(null)

  // Results state
  const [results, setResults] = useState(null)
  const [currentPage, setCurrentPage] = useState(0)
  const [isLoadingResults, setIsLoadingResults] = useState(false)

  // UI state
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [formError, setFormError] = useState(null)

  const pollingRef = useRef(null)

  // ── Helper: distinguishes "server unreachable" from other errors ──
  // A TypeError with this exact message is what fetch() throws when
  // the network request never even reached a server — DNS failure,
  // server down, CORS block before headers arrive, no internet, etc.
  // Every other error (4xx/5xx) is a real response from the server
  // that we've already parsed as JSON, so its message is meaningful
  // on its own.
  const describeError = (err) => {
    if (err instanceof TypeError && err.message === 'Failed to fetch') {
      return 'Could not reach the server. Please check your connection and try again.'
    }
    return err.message
  }

  // ── Polling ────────────────────────────────────────────────────
  useEffect(() => {
    if (!jobId) return

    const poll = async () => {
      try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}/status/`)
        const data = await response.json()

        setJobStatus(data.status)
        setJobProgress(data.progress)
        if (data.error_message) setJobError(data.error_message)

        const terminalStates = ['SUCCESS', 'FAILED', 'CANCELLED']
        if (terminalStates.includes(data.status)) {
          clearInterval(pollingRef.current)

          if (data.status === 'SUCCESS') {
            fetchResults(0)
          }
        }
      } catch (err) {
        // A single failed poll shouldn't stop the whole process —
        // log it and let the next scheduled poll try again.
        console.error('Polling error:', describeError(err))
      }
    }

    poll()
    pollingRef.current = setInterval(poll, POLL_INTERVAL_MS)
    return () => clearInterval(pollingRef.current)
  }, [jobId])

  // ── Fetch a page of results ────────────────────────────────────
  const fetchResults = async (page) => {
    if (!jobId) return
    setIsLoadingResults(true)

    try {
      const response = await fetch(
        `${API_BASE}/jobs/${jobId}/results/?page=${page}`
      )
      const data = await response.json()

      if (!response.ok) throw new Error(data.error || 'Could not load results')

      setResults(data)
      setCurrentPage(page)
    } catch (err) {
      setJobError(`Could not load results: ${describeError(err)}`)
    } finally {
      setIsLoadingResults(false)
    }
  }

  // ── File selection ─────────────────────────────────────────────
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
      setFormError(`Could not read file: ${describeError(err)}`)
      setFile(null)
    } finally {
      setIsLoadingColumns(false)
    }
  }

  // ── Form submission ────────────────────────────────────────────
  const handleSubmit = async () => {
    if (!file || !nlPrompt || !targetColumn || !replacementValue) {
      setFormError('Please fill in all fields and select a file.')
      return
    }

    // Guards against rapid double-clicks creating duplicate jobs
    // while the first request is still in flight.
    if (isSubmitting) return

    setIsSubmitting(true)
    setFormError(null)
    setJobId(null)
    setJobStatus(null)
    setJobProgress(0)
    setJobError(null)
    setResults(null)

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

      setJobId(data.id)
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  // ── Cancellation ───────────────────────────────────────────────
  const handleCancel = async () => {
    if (!jobId) return
    try {
      const response = await fetch(`${API_BASE}/jobs/${jobId}/cancel/`, {
        method: 'POST',
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.error || 'Could not cancel job')
      }
    } catch (err) {
      // Surface this rather than swallowing it — a failed cancel
      // attempt is something the user should know about.
      setJobError(`Cancel failed: ${describeError(err)}`)
    }
  }

  // ── Render helpers ─────────────────────────────────────────────
  const renderJobStatus = () => {
    if (!jobId) return null

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

        <div style={{
          background: '#eee',
          borderRadius: '4px',
          height: '20px',
          overflow: 'hidden',
          marginBottom: '0.5rem'
        }}>
          <div style={{
            background: jobStatus === 'FAILED' ? '#e55' :
                        jobStatus === 'CANCELLED' ? '#aaa' : '#4a9',
            width: `${jobProgress}%`,
            height: '100%',
            transition: 'width 0.3s ease',
          }} />
        </div>
        <p style={{ textAlign: 'center', margin: '0 0 1rem' }}>{jobProgress}%</p>

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

        {jobError && (
          <div style={{ color: 'red', marginTop: '1rem' }}>
            Error: {jobError}
          </div>
        )}

        {jobStatus === 'CANCELLED' && (
          <div style={{ color: '#888', marginTop: '1rem' }}>
            Job was cancelled.
          </div>
        )}
      </div>
    )
  }

  const renderResults = () => {
    if (!results) return null

    const { rows, columns, total_rows, total_pages, page } = results

    // Empty-file case — job succeeded but there's genuinely nothing
    // to show. Distinct from an error: nothing went wrong here.
    if (total_rows === 0) {
      return (
        <div style={{
          marginTop: '2rem',
          padding: '1.5rem',
          textAlign: 'center',
          color: '#888',
          border: '1px dashed #ccc',
          borderRadius: '8px'
        }}>
          <p style={{ margin: 0 }}>
            The job completed successfully, but the source file has no data rows.
          </p>
        </div>
      )
    }

    return (
      <div style={{ marginTop: '2rem' }}>
        <h3>
          Results — {total_rows.toLocaleString()} rows total
        </h3>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
          marginBottom: '1rem'
        }}>
          <button
            onClick={() => fetchResults(page - 1)}
            disabled={page === 0 || isLoadingResults}
            style={{ padding: '0.4rem 0.8rem' }}
          >
            ← Previous
          </button>

          <span>Page {page + 1} of {total_pages}</span>

          <button
            onClick={() => fetchResults(page + 1)}
            disabled={page >= total_pages - 1 || isLoadingResults}
            style={{ padding: '0.4rem 0.8rem' }}
          >
            Next →
          </button>
        </div>

        {isLoadingResults && <p>Loading...</p>}

        {rows.length === 0 ? (
          <p style={{ color: '#888' }}>No rows found on this page.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.9rem'
            }}>
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th key={col} style={{
                      padding: '0.5rem',
                      background: '#f0f0f0',
                      border: '1px solid #ddd',
                      textAlign: 'left',
                      whiteSpace: 'nowrap'
                    }}>
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, rowIndex) => (
                  <tr key={rowIndex} style={{
                    background: rowIndex % 2 === 0 ? 'white' : '#fafafa'
                  }}>
                    {columns.map((col) => (
                      <td key={col} style={{
                        padding: '0.4rem 0.5rem',
                        border: '1px solid #ddd',
                        maxWidth: '200px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap'
                      }}>
                        {row[col] === null ? (
                          <span style={{ color: '#aaa' }}>null</span>
                        ) : (
                          String(row[col])
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    )
  }

  // ── Main render ────────────────────────────────────────────────
  return (
    <div style={{ padding: '2rem', maxWidth: '900px', margin: '0 auto' }}>
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
      {renderResults()}

    </div>
  )
}

export default App