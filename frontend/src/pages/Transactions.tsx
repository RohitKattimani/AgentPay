import { useEffect, useState } from 'react'
import { paymentApi } from '../services/api'

export default function Transactions() {
  const [transactions, setTransactions] = useState<any[]>([])

  useEffect(() => {
    loadTransactions()
  }, [])

  const loadTransactions = async () => {
    try {
      const res = await paymentApi.list()
      setTransactions(res.data || [])
    } catch (e) {
      console.log('No transactions yet')
    }
  }

  const statusColor = (status: string) => {
    switch (status) {
      case 'captured': return 'text-green-400 bg-green-500/10'
      case 'authorized': return 'text-blue-400 bg-blue-500/10'
      case 'awaiting_approval': return 'text-yellow-300 bg-yellow-500/10'
      case 'failed': return 'text-red-400 bg-red-500/10'
      case 'held': return 'text-yellow-400 bg-yellow-500/10'
      default: return 'text-white/40 bg-white/10'
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Transactions</h1>
        <p className="text-white/50">Authorization, settlement, and payment-hold history</p>
      </div>

      <div className="glass-card p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-white/10">
                <th className="pb-3 text-xs font-medium text-white/50">Transaction ID</th>
                <th className="pb-3 text-xs font-medium text-white/50">Task</th>
                <th className="pb-3 text-xs font-medium text-white/50">Seller</th>
                <th className="pb-3 text-xs font-medium text-white/50">Amount</th>
                <th className="pb-3 text-xs font-medium text-white/50">Verification</th>
                <th className="pb-3 text-xs font-medium text-white/50">Payment Status</th>
                <th className="pb-3 text-xs font-medium text-white/50">Date</th>
              </tr>
            </thead>
            <tbody>
              {transactions.length > 0 ? (
                transactions.map((tx) => (
                  <tr key={tx.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                    <td className="py-3 text-white font-mono text-sm">{tx.id}</td>
                    <td className="py-3 text-white text-sm">{tx.task_name}</td>
                    <td className="py-3 text-white text-sm">{tx.seller}</td>
                    <td className="py-3 text-white font-medium text-sm">${tx.amount.toFixed(2)}</td>
                    <td className="py-3 text-sm">
                      <span className={`px-2 py-1 rounded text-xs ${statusColor(tx.verification_status)}`}>
                        {tx.verification_status}
                      </span>
                    </td>
                    <td className="py-3 text-sm">
                      <span className={`px-2 py-1 rounded text-xs ${statusColor(tx.payment_status)}`}>
                        {tx.payment_status}
                      </span>
                    </td>
                    <td className="py-3 text-white/50 text-xs text-sm">{tx.created_at || 'N/A'}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-white/40">No transactions yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
