// ─────────────────────────────────────────────────────────────
// useJob — owns the entire lifecycle of one job: submission,
// polling, terminal-state detection, cancellation, and result
// pagination. Components consume this hook and render; none of
// them know polling exists. This is the piece that makes the
// UI testable: the lifecycle logic lives in exactly one place.
// ─────────────────────────────────────────────────────────────

import { useState, useEffect, useRef, useCallback } from 'react'
import {
  createJob,
  fetchJobStatus,
  cancelJob,
  fetchResults,
  describeError,
} from '../api/client'

const POLL_INTERVAL_MS = 2000
const TERMINAL_STATES = ['SUCCESS', 'FAILED', 'CANCELLED']

export function useJob() {
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState(null)
  const [progress, setProgress] = useState(0)
  const [jobError, setJobError] = useState(null)

  const [results, setResults] = useState(null)
  const [isLoadingResults, setIsLoadingResults] = useState(false)

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  const pollingRef = useRef(null)

  const loadResultsPage = useCallback(async (id, page) => {
    setIsLoadingResults(true)
    try {
      const data = await fetchResults(id, page)
      setResults(data)
    } catch (err) {
      setJobError(`Could not load results: ${describeError(err)}`)
    } finally {
      setIsLoadingResults(false)
    }
  }, [])

  // Polling loop — starts when jobId is set, self-terminates on
  // any terminal state, cleans up on unmount or job change.
  useEffect(() => {
    if (!jobId) return

    const poll = async () => {
      try {
        const data = await fetchJobStatus(jobId)
        setStatus(data.status)
        setProgress(data.progress)
        if (data.error_message) setJobError(data.error_message)

        if (TERMINAL_STATES.includes(data.status)) {
          clearInterval(pollingRef.current)
          if (data.status === 'SUCCESS') {
            loadResultsPage(jobId, 0)
          }
        }
      } catch (err) {
        // A single failed poll shouldn't kill the loop; the next
        // scheduled tick retries.
        console.error('Polling error:', describeError(err))
      }
    }

    poll()
    pollingRef.current = setInterval(poll, POLL_INTERVAL_MS)
    return () => clearInterval(pollingRef.current)
  }, [jobId, loadResultsPage])

  const submit = useCallback(async (formValues) => {
    if (isSubmitting) return

    setIsSubmitting(true)
    setSubmitError(null)
    setJobId(null)
    setStatus(null)
    setProgress(0)
    setJobError(null)
    setResults(null)

    try {
      const data = await createJob(formValues)
      setJobId(data.id)
    } catch (err) {
      setSubmitError(describeError(err))
    } finally {
      setIsSubmitting(false)
    }
  }, [isSubmitting])

  const cancel = useCallback(async () => {
    if (!jobId) return
    try {
      await cancelJob(jobId)
      // Polling detects CANCELLED on its next tick and stops itself.
    } catch (err) {
      setJobError(`Cancel failed: ${describeError(err)}`)
    }
  }, [jobId])

  const goToPage = useCallback((page) => {
    if (jobId) loadResultsPage(jobId, page)
  }, [jobId, loadResultsPage])

  return {
    jobId,
    status,
    progress,
    jobError,
    results,
    isLoadingResults,
    isSubmitting,
    submitError,
    submit,
    cancel,
    goToPage,
  }
}
