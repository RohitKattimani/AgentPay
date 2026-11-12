import { useEffect, useState } from 'react'
import { getActiveTaskId, verificationApi } from '../services/api'

interface Report {
  task_id: number
  missing_values: number
  empty_output: number
  duplicate_records: number
  invalid_emails: number
  formatting_errors: number
  verification_status: string
  report_text: string
  revision_count: number
}

export default function VerificationCenter() {
  const taskId = getActiveTaskId()
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadReport = async () => {
    if (!taskId) return
    try {
      const response = await verificationApi.get(taskId)
      setReport(response.data as Report)
      setError('')
    } catch (err: any) {
      setReport(null)
      setError(err.response?.data?.detail || 'No verification report is available yet.')
    }
  }

  useEffect(() => { loadReport() }, [taskId])

  const runVerification = async () => {
    if (!taskId) return
    setLoading(true)
    setError('')
    try {
      const response = await verificationApi.run(taskId)
      setReport(response.data as Report)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Verification could not be completed.')
    } finally {
      setLoading(false)
    }
  }

  const statusClass = report?.verification_status === 'pass'
    ? 'bg-green-500/10 text-green-300 border-green-500/30'
    : report?.verification_status === 'fail'
      ? 'bg-red-500/10 text-red-300 border-red-500/30'
      : 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Verification center</h1>
        <p className="text-white/50">Independent checks run before any payment can be captured.</p>
      </div>
      {!taskId ? (
        <div className="glass-card p-6 text-white/60">Create a task first to inspect its verification report.</div>
      ) : !report ? (
        <div className="glass-card p-6 text-center space-y-3">
          <p className="text-white/60">{error || 'No verification report yet.'}</p>
          <button onClick={loadReport} className="btn-secondary">Refresh report</button>
        </div>
      ) : (
        <div className="glass-card p-6 space-y-6">
          <div>
            <div className={`inline-flex items-center rounded-lg border px-4 py-2 text-sm font-semibold ${statusClass}`}>{report.verification_status.replace(/_/g, ' ').toUpperCase()}</div>
            <p className="text-sm text-white/65 mt-3">{report.report_text}</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Metric label="Missing values" value={report.missing_values} />
            <Metric label="Empty output" value={report.empty_output} />
            <Metric label="Duplicate records" value={report.duplicate_records} />
            <Metric label="Invalid emails" value={report.invalid_emails} />
            <Metric label="Formatting errors" value={report.formatting_errors} />
          </div>
          <div className="flex flex-wrap gap-3">
            <button onClick={runVerification} disabled={loading} className="btn-secondary disabled:opacity-50">{loading ? 'Checking...' : 'Run checks again'}</button>
            <a href={`/api/tasks/${taskId}/download`} className="btn-primary">Download cleaned CSV</a>
          </div>
        </div>
      )}
      {error && report && <p role="alert" className="text-sm text-red-300">{error}</p>}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="bg-white/5 border border-white/10 rounded-lg p-4"><p className="text-xs text-white/45 mb-1">{label}</p><p className="text-2xl font-bold">{value}</p></div>
}
