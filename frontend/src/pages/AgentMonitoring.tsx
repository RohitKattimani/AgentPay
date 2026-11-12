import { useEffect, useState } from 'react'
import { agentsApi } from '../services/api'

export default function AgentMonitoring() {
  const [agents, setAgents] = useState<any[]>([])

  useEffect(() => {
    agentsApi.list().then((res) => setAgents(res.data || []))
  }, [])

  const statusColor = (status: string) => {
    switch (status) {
      case 'busy': return 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
      case 'error': return 'bg-red-500/20 text-red-400 border border-red-500/30'
      default: return 'bg-white/10 text-white/40 border border-white/10'
    }
  }

  const agentDescriptions: Record<string, string> = {
    'Buyer Agent': 'Decomposes user tasks into deliverables',
    'Negotiation Agent': 'Collects bids and selects best seller',
    'Contract Agent': 'Generates digital agreements',
    'Seller Agent': 'Executes tasks and produces deliverables',
    'Independent Verification Agent': 'Verifies seller deliverables',
    'PayPal Payment Agent': 'Authorizes and captures payments',
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Agent Monitoring</h1>
        <p className="text-white/50">Monitor the six specialized agents and their latest activity</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {agents.map((agent) => (
          <div key={agent.name} className="glass-card p-5">
            <div className="flex justify-between items-start mb-3">
              <div>
                <h3 className="font-semibold text-white">{agent.name}</h3>
                <p className="text-xs text-white/50">{agentDescriptions[agent.name] || ''}</p>
              </div>
              <span className={`px-2 py-1 rounded text-xs font-medium ${statusColor(agent.status)}`}>
                {agent.status}
              </span>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-white/50">Last Activity</span>
                <span className="text-white">{agent.last_activity || 'none'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-white/50">Events</span>
                <span className="text-white">{agent.event_count}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
