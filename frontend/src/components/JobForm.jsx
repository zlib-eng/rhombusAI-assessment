// ─────────────────────────────────────────────────────────────
// JobForm — owns all form state and client-side validation.
// Structure encodes the pipeline: Source → Transformation → Run.
// Reports a completed submission upward via onSubmit; knows
// nothing about jobs, polling, or results.
// ─────────────────────────────────────────────────────────────

import { useState } from 'react'
import { fetchColumns, describeError } from '../api/client'

const TRANSFORMATION_TYPES = {
  FIND_REPLACE: 'Find and replace',
  EXTRACT: 'Extract to new column',
  STANDARDIZE_FORMAT: 'Standardize format',
}

export default function JobForm({ onSubmit, isSubmitting, submitError }) {
  const [file, setFile] = useState(null)
  const [nlPrompt, setNlPrompt] = useState('')
  const [targetColumn, setTargetColumn] = useState('')
  const [transformationType, setTransformationType] = useState('FIND_REPLACE')
  const [replacementValue, setReplacementValue] = useState('')
  const [outputColumnName, setOutputColumnName] = useState('')

  const [availableColumns, setAvailableColumns] = useState([])
  const [isLoadingColumns, setIsLoadingColumns] = useState(false)
  const [formError, setFormError] = useState(null)
  const [formWarning, setFormWarning] = useState(null)

  const handleFileChange = async (e) => {
    const selectedFile = e.target.files[0]
    if (!selectedFile) return

    setFile(selectedFile)
    setAvailableColumns([])
    setTargetColumn('')
    setFormError(null)
    setFormWarning(null)
    setIsLoadingColumns(true)

    try {
      const data = await fetchColumns(selectedFile)
      setAvailableColumns(data.columns)
      if (data.columns.length > 0) setTargetColumn(data.columns[0])
      if (data.warning) setFormWarning(data.warning)
    } catch (err) {
      setFormError(`Could not read file: ${describeError(err)}`)
      setFile(null)
    } finally {
      setIsLoadingColumns(false)
    }
  }

  const validate = () => {
    if (!file || !nlPrompt || !targetColumn) {
      return 'Choose a file, describe the pattern, and pick a column.'
    }
    if (transformationType === 'FIND_REPLACE' && !replacementValue) {
      return 'Enter a replacement value.'
    }
    if (transformationType === 'EXTRACT' && !outputColumnName) {
      return 'Name the new column.'
    }
    return null
  }

  const handleSubmit = () => {
    const error = validate()
    if (error) {
      setFormError(error)
      return
    }
    setFormError(null)
    onSubmit({
      file,
      nlPrompt,
      targetColumn,
      transformationType,
      replacementValue,
      outputColumnName,
    })
  }

  const submitDisabled =
    isSubmitting ||
    availableColumns.length === 0 ||
    (transformationType === 'FIND_REPLACE' && !replacementValue) ||
    (transformationType === 'EXTRACT' && !outputColumnName)

  return (
    <div>
      {/* ── Group 1: Source ─────────────────────────────────── */}
      <section className="field-group" aria-labelledby="legend-source">
        <h2 className="field-group__legend" id="legend-source">Source</h2>

        <div className="field">
          <label htmlFor="file-input">Data file</label>
          <input
            id="file-input"
            type="file"
            accept=".csv,.xlsx"
            onChange={handleFileChange}
          />
          <p className="hint">
            {isLoadingColumns
              ? 'Reading columns…'
              : 'CSV or Excel. Columns load automatically.'}
          </p>
        </div>

        <div className="field">
          <label htmlFor="column-select">Target column</label>
          {availableColumns.length > 0 ? (
            <select
              id="column-select"
              value={targetColumn}
              onChange={(e) => setTargetColumn(e.target.value)}
            >
              {availableColumns.map((col) => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              placeholder="Choose a file to see its columns"
              disabled
            />
          )}
        </div>
      </section>

      {/* ── Group 2: Transformation ─────────────────────────── */}
      <section className="field-group" aria-labelledby="legend-transform">
        <h2 className="field-group__legend" id="legend-transform">Transformation</h2>

        <div className="field">
          <label htmlFor="type-select">Operation</label>
          <select
            id="type-select"
            value={transformationType}
            onChange={(e) => setTransformationType(e.target.value)}
          >
            {Object.entries(TRANSFORMATION_TYPES).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="prompt-input">Describe the pattern</label>
          <input
            id="prompt-input"
            type="text"
            placeholder="e.g. find email addresses"
            value={nlPrompt}
            onChange={(e) => setNlPrompt(e.target.value)}
          />
        </div>

        {transformationType === 'FIND_REPLACE' && (
          <div className="field">
            <label htmlFor="replacement-input">Replace matches with</label>
            <input
              id="replacement-input"
              type="text"
              placeholder="e.g. REDACTED"
              value={replacementValue}
              onChange={(e) => setReplacementValue(e.target.value)}
            />
          </div>
        )}

        {transformationType === 'EXTRACT' && (
          <div className="field">
            <label htmlFor="output-col-input">New column name</label>
            <input
              id="output-col-input"
              type="text"
              placeholder="e.g. area_code"
              value={outputColumnName}
              onChange={(e) => setOutputColumnName(e.target.value)}
            />
          </div>
        )}
      </section>

      {/* ── Group 3: Run ────────────────────────────────────── */}
      <button
        className="btn btn--primary"
        onClick={handleSubmit}
        disabled={submitDisabled}
      >
        {isSubmitting ? 'Submitting…' : 'Run transformation'}
      </button>

      {formWarning && (
        <div className="banner banner--warn" role="status">
          {formWarning}
        </div>
      )}

      {(formError || submitError) && (
        <div className="banner banner--error" role="alert">
          {formError || submitError}
        </div>
      )}
    </div>
  )
}
