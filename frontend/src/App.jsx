import { useState } from 'react'

const API_BASE = 'http://localhost:8000/api'

function App() {
  // Form field values
  const [file, setFile] = useState(null)
  const [nlPrompt, setNlPrompt] = useState('')
  const [targetColumn, setTargetColumn] = useState('')
  const [replacementValue, setReplacementValue] = useState('')

  // UI state
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [jobId, setJobId] = useState(null)

  const handleSubmit = async () => {
    // Basic client-side validation before we even hit the network
    if (!file || !nlPrompt || !targetColumn || !replacementValue) {
      setError('Please fill in all fields and select a file.')
      return
    }

    setIsLoading(true)
    setError(null)
    setJobId(null)

    // FormData is how you send files over HTTP.
    // It's the JavaScript equivalent of a multipart form upload.
    const formData = new FormData()
    formData.append('file', file)
    formData.append('nl_prompt', nlPrompt)
    formData.append('target_column', targetColumn)
    formData.append('replacement_value', replacementValue)

    try {
      const response = await fetch(`${API_BASE}/jobs/`, {
        method: 'POST',
        body: formData,
        // Do NOT set Content-Type header manually when using FormData.
        // The browser sets it automatically with the correct boundary.
      })

      const data = await response.json()

      if (!response.ok) {
        // Django returned an error — show it to the user
        const errorMessage = data.error || JSON.stringify(data)
        throw new Error(errorMessage)
      }

      // Success — store the job ID
      setJobId(data.id)

    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '600px', margin: '0 auto' }}>
      <h1>RhombusAI — Data Processor</h1>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

        <div>
          <label>Upload CSV or Excel file</label><br />
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => setFile(e.target.files[0])}
          />
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
          <label>Target column name</label><br />
          <input
            type="text"
            placeholder="e.g. Email"
            value={targetColumn}
            onChange={(e) => setTargetColumn(e.target.value)}
            style={{ width: '100%', padding: '0.5rem' }}
          />
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
          disabled={isLoading}
          style={{ padding: '0.75rem', cursor: 'pointer' }}
        >
          {isLoading ? 'Submitting...' : 'Submit Job'}
        </button>

        {error && (
          <div style={{ color: 'red', padding: '1rem', background: '#fee' }}>
            Error: {error}
          </div>
        )}

        {jobId && (
          <div style={{ color: 'green', padding: '1rem', background: '#efe' }}>
            <strong>Job created successfully!</strong><br />
            Job ID: {jobId}
          </div>
        )}

      </div>
    </div>
  )
}

export default App