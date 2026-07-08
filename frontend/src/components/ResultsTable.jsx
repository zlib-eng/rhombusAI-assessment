// ─────────────────────────────────────────────────────────────
// ResultsTable — renders one page of processed output with
// pagination controls. Pure presentation: receives data and a
// page-change callback, holds no fetching logic of its own.
// ─────────────────────────────────────────────────────────────

export default function ResultsTable({ results, isLoading, onPageChange }) {
  if (!results) return null

  const { rows, columns, total_rows, total_pages, page } = results

  if (total_rows === 0) {
    return (
      <div className="empty-state">
        The job completed, but the source file has no data rows.
      </div>
    )
  }

  return (
    <div className="results">
      <div className="results__header">
        <span className="results__count">
          {total_rows.toLocaleString()} row{total_rows !== 1 ? 's' : ''} processed
        </span>

        <div className="pagination">
          <button
            className="btn btn--ghost"
            onClick={() => onPageChange(page - 1)}
            disabled={page === 0 || isLoading}
          >
            ← Prev
          </button>
          <span className="pagination__page">
            {page + 1} / {total_pages}
          </span>
          <button
            className="btn btn--ghost"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= total_pages - 1 || isLoading}
          >
            Next →
          </button>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col} scope="col">{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((col) => (
                  <td key={col} title={row[col] === null ? '' : String(row[col])}>
                    {row[col] === null
                      ? <span className="null">null</span>
                      : String(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
