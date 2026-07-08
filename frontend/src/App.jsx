// ─────────────────────────────────────────────────────────────
// App — pure composition. All lifecycle logic lives in useJob;
// all form logic in JobForm; all presentation in JobStatus and
// ResultsTable. This file just wires them together.
// ─────────────────────────────────────────────────────────────

import './styles/tokens.css'
import { useJob } from './hooks/useJob'
import JobForm from './components/JobForm'
import JobStatus from './components/JobStatus'
import ResultsTable from './components/ResultsTable'

export default function App() {
  const job = useJob()

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>rhombus // data processor</h1>
        <span className="tagline">nl → regex → spark</span>
      </header>

      <JobForm
        onSubmit={job.submit}
        isSubmitting={job.isSubmitting}
        submitError={job.submitError}
      />

      <JobStatus
        jobId={job.jobId}
        status={job.status}
        progress={job.progress}
        jobError={job.jobError}
        onCancel={job.cancel}
      />

      <ResultsTable
        results={job.results}
        isLoading={job.isLoadingResults}
        onPageChange={job.goToPage}
      />
    </div>
  )
}
