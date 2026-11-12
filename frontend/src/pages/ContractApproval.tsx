import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { contractApi, getActiveTaskId } from '../services/api'

interface Contract {
  id: number
  task_id: number
  seller_name: string
  agreed_price: number
  deadline_minutes: number
  deliverables: string
  acceptance_criteria: string
  revision_policy: string
  payment_conditions: string
  status: string
  buyer_approved: boolean
}

function formatList(value: string) {
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : [value]
  } catch {
    return [value]
  }
}

export default function ContractApproval() {
  const taskId = getActiveTaskId()
  const [contract, setContract] = useState<Contract | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [approvalUrl, setApprovalUrl] = useState('')
  const [error, setError] = useState('')

  const loadContract = async () => {
    if (!taskId) return
    try {
      const response = await contractApi.get(taskId)
      setContract(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'No contract has been generated for this task yet.')
    }
  }

  useEffect(() => { loadContract() }, [taskId])

  const approve = async () => {
    if (!taskId) return
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const response = await contractApi.approve(taskId)
      if (response.data.approval_url) {
        setApprovalUrl(response.data.approval_url)
        setMessage('Contract approved. Continue to PayPal to authorize the payment before execution begins.')
        setContract((current) => current ? { ...current, status: 'approved', buyer_approved: true } : current)
      } else {
        setMessage(response.data.status === 'completed'
          ? 'Contract approved. Verification passed and the payment was captured in demo mode.'
          : response.data.message || 'Contract approval was processed.')
        await loadContract()
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'The contract could not be approved.')
    } finally {
      setLoading(false)
    }
  }

  const reject = async () => {
    if (!taskId) return
    setLoading(true)
    setError('')
    try {
      await contractApi.reject(taskId)
      setMessage('Contract rejected. The task has been cancelled.')
      setContract((current) => current ? { ...current, status: 'rejected' } : current)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'The contract could not be rejected.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Contract approval</h1>
        <p className="text-white/50">Review the terms before authorizing the seller to begin work.</p>
      </div>

      {!taskId ? (
        <div className="glass-card p-6 text-center text-white/60">Create a task to generate a contract.</div>
      ) : !contract ? (
        <div className="glass-card p-6 text-center space-y-3">
          <p className="text-white/60">{error || 'Loading contract...'}</p>
          <button onClick={loadContract} className="btn-secondary">Refresh contract</button>
          <p><Link to="/create" className="text-blue-300 text-sm hover:underline">Create a new task</Link></p>
        </div>
      ) : (
        <div className="glass-card p-6">
          <div className="flex flex-wrap justify-between items-start gap-4 mb-6">
            <div>
              <h2 className="text-lg font-semibold">Work agreement #{contract.id}</h2>
              <p className="text-xs text-white/40 mt-1">Task #{contract.task_id}</p>
            </div>
            <span className={`text-xs px-3 py-1 rounded-full ${contract.status === 'approved' || contract.status === 'completed' ? 'bg-green-500/10 text-green-300' : contract.status === 'rejected' ? 'bg-red-500/10 text-red-300' : 'bg-yellow-500/10 text-yellow-300'}`}>
              {contract.status.replace(/_/g, ' ')}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
            <div className="bg-white/5 rounded-lg p-4"><p className="text-xs text-white/40 mb-1">Selected seller</p><p className="font-medium">{contract.seller_name}</p></div>
            <div className="bg-white/5 rounded-lg p-4"><p className="text-xs text-white/40 mb-1">Agreed price</p><p className="text-2xl font-bold">${contract.agreed_price.toFixed(2)} <span className="text-xs text-white/40 font-normal">USD</span></p></div>
            <div className="bg-white/5 rounded-lg p-4"><p className="text-xs text-white/40 mb-1">Delivery estimate</p><p className="font-medium">{contract.deadline_minutes} minutes</p></div>
            <div className="bg-white/5 rounded-lg p-4"><p className="text-xs text-white/40 mb-1">Buyer approval</p><p className="font-medium">{contract.buyer_approved ? 'Approved' : 'Pending'}</p></div>
          </div>

          <div className="space-y-4">
            <section className="bg-white/5 rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-2">Deliverables</h3>
              <ul className="list-disc list-inside space-y-1 text-sm text-white/75">{formatList(contract.deliverables).map((item: string, index: number) => <li key={index}>{item}</li>)}</ul>
            </section>
            <section className="bg-white/5 rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-2">Acceptance criteria</h3>
              <ul className="list-disc list-inside space-y-1 text-sm text-white/75">{formatList(contract.acceptance_criteria).map((item: string, index: number) => <li key={index}>{item}</li>)}</ul>
            </section>
            <section className="bg-white/5 rounded-lg p-4"><h3 className="text-sm font-semibold mb-1">Revision policy</h3><p className="text-sm text-white/65">{contract.revision_policy}</p></section>
            <section className="bg-white/5 rounded-lg p-4"><h3 className="text-sm font-semibold mb-1">Payment conditions</h3><p className="text-sm text-white/65">{contract.payment_conditions}</p></section>
          </div>

          {contract.status === 'pending_approval' && (
            <div className="mt-8 flex flex-col sm:flex-row gap-3">
              <button onClick={approve} disabled={loading} className="btn-primary flex-1 disabled:opacity-50">{loading ? 'Processing...' : 'Approve contract'}</button>
              <button onClick={reject} disabled={loading} className="btn-danger flex-1 disabled:opacity-50">Reject contract</button>
            </div>
          )}

          {approvalUrl && <a href={approvalUrl} className="btn-primary block text-center mt-5">Continue to PayPal</a>}
          {message && <div role="status" className="mt-5 rounded-lg bg-blue-500/10 border border-blue-500/20 p-4 text-sm text-blue-200">{message}</div>}
          {error && <div role="alert" className="mt-5 rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-sm text-red-200">{error}</div>}
          {(contract.status === 'completed') && <a href={`/api/tasks/${taskId}/download`} className="btn-secondary block text-center mt-4">Download cleaned CSV</a>}
        </div>
      )}
    </div>
  )
}
