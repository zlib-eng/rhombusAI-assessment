// ─────────────────────────────────────────────────────────────
// API client — the single place the frontend talks to Django.
// Components never call fetch() directly; they call these
// functions. Swapping the backend URL, adding auth headers, or
// changing error handling happens here and nowhere else.
// ─────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

// fetch() throws TypeError('Failed to fetch') when the request
// never reached a server at all. Everything else is a real
// response whose parsed error message is meaningful on its own.
export function describeError(err) {
  if (err instanceof TypeError && err.message === 'Failed to fetch') {
    return 'Could not reach the server. Please check your connection and try again.'
  }
  return err.message
}

async function parseOrThrow(response, fallbackMessage) {
  const data = await response.json()
  if (!response.ok) {
    throw new Error(data.error || fallbackMessage || JSON.stringify(data))
  }
  return data
}

export async function fetchColumns(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE}/jobs/columns/`, {
    method: 'POST',
    body: formData,
  })
  return parseOrThrow(response, 'Could not read columns')
}

export async function createJob({
  file,
  nlPrompt,
  targetColumn,
  transformationType,
  replacementValue,
  outputColumnName,
}) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('nl_prompt', nlPrompt)
  formData.append('target_column', targetColumn)
  formData.append('transformation_type', transformationType)
  if (transformationType === 'FIND_REPLACE') {
    formData.append('replacement_value', replacementValue)
  }
  if (transformationType === 'EXTRACT') {
    formData.append('output_column_name', outputColumnName)
  }

  const response = await fetch(`${API_BASE}/jobs/`, {
    method: 'POST',
    body: formData,
  })
  return parseOrThrow(response)
}

export async function fetchJobStatus(jobId) {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/status/`)
  return parseOrThrow(response, 'Could not fetch job status')
}

export async function cancelJob(jobId) {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/cancel/`, {
    method: 'POST',
  })
  return parseOrThrow(response, 'Could not cancel job')
}

export async function fetchResults(jobId, page) {
  const response = await fetch(
    `${API_BASE}/jobs/${jobId}/results/?page=${page}`
  )
  return parseOrThrow(response, 'Could not load results')
}
