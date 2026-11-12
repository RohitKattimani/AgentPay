import { useEffect, useState } from 'react'
import { getActiveTaskId, negotiationApi } from '../services/api'

interface Bid {
  id: number
  seller_name: string
  price: number
  delivery_minutes: number
  rating: number
  score?: number
  is_winner: boolean
}

export default function NegotiationCenter() {
  const [bids, setBids] = useState<Bid[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const taskId = getActiveTaskId()

  useEffect(() => {
    if (!taskId) return
    negotiationApi.getBids(taskId)
      .then((response) => setBids(response.data || []))
      .catch(() => setError('Could not load bids for the active task.'))
  }, [taskId])

  const startNegotiation = async () => {
    if (!taskId) return
    setLoading(true)
    setError('')
    try {
      const response = await negotiationApi.start(taskId)
      setBids(response.data.all_bids || [])
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Negotiation could not be completed.')
    } finally {
      setLoading(false)
    }
  }

  const winner = bids.find((bid) => bid.is_winner)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Negotiation center</h1>
        <p className="text-white/50">Compare eligible seller bids and review the weighted selection.</p>
      </div>
      {!taskId ? (
        <div className="glass-card p-6 text-white/60">Create a task first to see its seller bids.</div>
      ) : (
        <div className="glass-card p-6">
          <div className="flex flex-wrap justify-between items-center gap-3 mb-6">
            <div>
              <h2 className="text-lg font-semibold">Seller bids</h2>
              <p className="text-xs text-white/40">Active task #{taskId}</p>
            </div>
            <button onClick={startNegotiation} disabled={loading || bids.length > 0} className="btn-secondary disabled:opacity-50">
              {bids.length > 0 ? 'Bids received' : loading ? 'Negotiating...' : 'Start negotiation'}
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead><tr className="border-b border-white/10">
                {['Seller', 'Price', 'Delivery', 'Rating', 'Score', 'Selection'].map((heading) => <th key={heading} className="pb-3 pr-4 text-xs font-medium text-white/50">{heading}</th>)}
              </tr></thead>
              <tbody>
                {bids.map((bid) => (
                  <tr key={bid.id} className="border-b border-white/5">
                    <td className="py-3 pr-4 text-white font-medium">{bid.seller_name}</td>
                    <td className="py-3 pr-4 text-white">${bid.price.toFixed(2)}</td>
                    <td className="py-3 pr-4 text-white">{bid.delivery_minutes} min</td>
                    <td className="py-3 pr-4 text-white">{bid.rating.toFixed(1)}/5</td>
                    <td className="py-3 pr-4 text-white">{bid.score?.toFixed(1) ?? 'N/A'}</td>
                    <td className="py-3">{bid.is_winner ? <span className="text-green-300 text-xs">Selected</span> : <span className="text-white/40 text-xs">Eligible</span>}</td>
                  </tr>
                ))}
                {bids.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-white/40">No bids available for the active task.</td></tr>}
              </tbody>
            </table>
          </div>
          {winner && <div className="mt-5 rounded-lg bg-blue-500/10 border border-blue-500/20 p-4 text-sm text-white/80">
            <strong>{winner.seller_name}</strong> selected at <strong>${winner.price.toFixed(2)}</strong>. Selection weights: price 50%, delivery 25%, and rating 25%.
          </div>}
        </div>
      )}
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    </div>
  )
}
