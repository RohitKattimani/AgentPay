import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { setActiveTaskId, taskApi } from '../services/api'

interface WorkflowResult {
  task_id: number
  status: string
  buyer_result?: { decomposition?: { task_name: string; budget: number; deliverables: string[]; acceptance_criteria: string[] } }
  negotiation_result?: { winning_seller: string; winning_price: number; delivery_minutes: number }
  contract_result?: { contract_id: number; status: string }
}

export default function CreateTask() {
  const navigate = useNavigate()
  const [description, setDescription] = useState('Clean this CSV by removing duplicate records, standardizing column names and whitespace, and reporting missing or invalid data.')
  const [budget, setBudget] = useState(5)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<WorkflowResult | null>(null)
  const [error, setError] = useState('')

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!file) {
      setError('Choose a CSV file to continue.')
      return
    }
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const created = await taskApi.create({ description, budget, file })
      const taskId = created.data.task_id ?? created.data.id
      setActiveTaskId(taskId)
      const workflow = await taskApi.start(taskId)
      setResult(workflow.data as WorkflowResult)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'The task could not be created. Check that the API is running and the CSV is valid.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Create a task</h1>
        <p className="text-white/50">Submit a CSV work order to the AgentPay marketplace.</p>
      </div>

      <form onSubmit={handleSubmit} className="glass-card p-6 space-y-5">
        <div>
          <label htmlFor="description" className="block text-sm font-medium text-white/70 mb-2">Task description</label>
          <textarea
            id="description"
            className="w-full bg-white/5 border border-white/10 rounded-lg p-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
            rows={4}
            maxLength={2000}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            required
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div>
            <label htmlFor="budget" className="block text-sm font-medium text-white/70 mb-2">Maximum budget (USD)</label>
            <div className="flex items-center gap-2">
              <input
                id="budget"
                type="number"
                step="0.01"
                min="0.01"
                max="5"
                className="bg-white/5 border border-white/10 rounded-lg p-2 text-white focus:ring-2 focus:ring-blue-500 outline-none w-28"
                value={budget}
                onChange={(event) => setBudget(Number(event.target.value))}
                required
              />
              <span className="text-xs text-white/40">Maximum $5.00</span>
            </div>
          </div>

          <div>
            <label htmlFor="csv-file" className="block text-sm font-medium text-white/70 mb-2">Source CSV</label>
            <input
              id="csv-file"
              type="file"
              accept=".csv,text/csv"
              className="block w-full text-sm text-white/60 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-blue-500/20 file:text-blue-300 hover:file:bg-blue-500/30 cursor-pointer"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              required
            />
            <p className="text-xs text-white/40 mt-2">CSV only, up to 5 MB. Original values are preserved unless a row is an exact duplicate.</p>
          </div>
        </div>

        {file && <p className="text-xs text-white/50">Selected: {file.name} ({(file.size / 1024).toFixed(1)} KB)</p>}

        <button type="submit" disabled={loading || !description.trim() || !file || budget <= 0 || budget > 5} className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed">
          {loading ? 'Creating work order...' : 'Create and negotiate task'}
        </button>
      </form>

      {error && <div role="alert" className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-300 text-sm">{error}</div>}

      {result && (
        <div className="glass-card p-6 space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">Work order created</h2>
              <p className="text-sm text-white/50">Task #{result.task_id} is awaiting contract approval.</p>
            </div>
            <span className="text-xs px-3 py-1 rounded-full bg-yellow-500/10 text-yellow-300">{result.status.replace(/_/g, ' ')}</span>
          </div>
          {result.buyer_result?.decomposition && (
            <div className="space-y-2 text-sm">
              <p><span className="text-white/50">Budget:</span> ${result.buyer_result.decomposition.budget.toFixed(2)}</p>
              <div>
                <p className="text-white/50 mb-1">Deliverables</p>
                <ul className="list-disc list-inside text-white/80 space-y-1">
                  {result.buyer_result.decomposition.deliverables.map((item, index) => <li key={index}>{item}</li>)}
                </ul>
              </div>
            </div>
          )}
          {result.negotiation_result && (
            <p className="text-sm text-white/80">Selected seller: <strong>{result.negotiation_result.winning_seller}</strong> at ${result.negotiation_result.winning_price.toFixed(2)} with a {result.negotiation_result.delivery_minutes}-minute delivery estimate.</p>
          )}
          <button onClick={() => navigate('/contract')} className="btn-primary w-full">Review contract</button>
        </div>
      )}
    </div>
  )
}
