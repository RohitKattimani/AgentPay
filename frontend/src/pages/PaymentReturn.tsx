import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { paymentApi, setActiveTaskId } from '../services/api'

export default function PaymentReturn() {
  const [params] = useSearchParams()
  const [message, setMessage] = useState('Confirming the PayPal authorization...')
  const [error, setError] = useState('')
  const taskId = Number(params.get('task_id'))
  const orderId = params.get('token') || ''

  useEffect(() => {
    let active = true
    const complete = async () => {
      if (!Number.isInteger(taskId) || taskId <= 0 || !orderId) {
        setError('The PayPal return did not include a valid task and order reference. No work was started.')
        return
      }
      setActiveTaskId(taskId)
      try {
        const response = await paymentApi.completeAuthorization(taskId, orderId)
        if (!active) return
        setMessage(response.data.status === 'completed'
          ? 'Payment authorization confirmed. The seller completed the task and verification passed.'
          : `Payment authorization confirmed. Task status: ${response.data.status}.`)
      } catch (err: any) {
        if (active) setError(err.response?.data?.detail || 'Could not confirm the PayPal authorization.')
      }
    }
    complete()
    return () => { active = false }
  }, [taskId, orderId])

  return (
    <div className="max-w-2xl mx-auto glass-card p-8 space-y-4">
      <h1 className="text-2xl font-bold">Payment authorization</h1>
      {error ? <p role="alert" className="text-red-300 text-sm">{error}</p> : <p className="text-white/70 text-sm">{message}</p>}
      <div className="flex flex-wrap gap-3">
        {Number.isInteger(taskId) && taskId > 0 && <a href={`/api/tasks/${taskId}/download`} className="btn-primary">Download cleaned CSV</a>}
        <Link to="/contract" className="btn-secondary">Back to contract</Link>
        <Link to="/transactions" className="btn-secondary">View transactions</Link>
      </div>
    </div>
  )
}
