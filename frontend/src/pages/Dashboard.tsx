import { useEffect, useState } from 'react'
import { statsApi, DashboardStats } from '../services/api'

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats>({
    total_tasks: 0,
    active_tasks: 0,
    completed_tasks: 0,
    failed_tasks: 0,
    total_volume: 0,
    recent_activity: [],
  })

  useEffect(() => {
    statsApi.get().then((res) => setStats(res.data))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Dashboard</h1>
        <p className="text-white/50">Overview of your autonomous task marketplace</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard label="Total Tasks" value={stats.total_tasks} color="blue" icon="📋" />
        <StatCard label="Active Tasks" value={stats.active_tasks} color="violet" icon="⚡" />
        <StatCard label="Completed" value={stats.completed_tasks} color="green" icon="✅" />
        <StatCard label="Failed" value={stats.failed_tasks} color="red" icon="❌" />
        <StatCard label="Total Volume" value={`$${stats.total_volume.toFixed(2)}`} color="blue" icon="💰" />
        <StatCard label="Success Rate" value={
          stats.total_tasks > 0
            ? Math.round((stats.completed_tasks / stats.total_tasks) * 100) + '%'
            : '0%'
        } color="green" icon="📈" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold mb-4">Recent Agent Activity</h2>
          <div className="space-y-3">
            {stats.recent_activity.length > 0 ? (
              stats.recent_activity.map((activity, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
                  <div className="flex items-center gap-3">
                    <span className="text-sm">{activity.agent}</span>
                    <span className="text-xs text-white/40">{activity.time || ''}</span>
                  </div>
                  <span className="text-xs text-blue-400">{activity.event}</span>
                </div>
              ))
            ) : (
              <p className="text-white/40 text-sm">No recent activity</p>
            )}
          </div>
        </div>

        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold mb-4">Task Distribution</h2>
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm text-white/60">Completed</span>
            <span className="text-sm">{stats.completed_tasks}</span>
          </div>
          <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500"
              style={{
                width: stats.total_tasks > 0 ? (stats.completed_tasks / stats.total_tasks) * 100 : 0,
              }}
            />
          </div>
          <div className="flex items-center justify-between mt-2">
            <span className="text-sm text-white/60">Pending/Active</span>
            <span className="text-sm">{stats.active_tasks}</span>
          </div>
          <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden">
            <div className="h-full bg-violet-500" style={{ width: stats.total_tasks > 0 ? (stats.active_tasks / stats.total_tasks) * 100 : 0 }} />
          </div>
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, color, icon }: { label: string; value: string | number; color: string; icon: string }) {
  const colorClasses: Record<string, string> = {
    blue: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
    violet: 'bg-violet-500/20 text-violet-400 border border-violet-500/30',
    green: 'bg-green-500/20 text-green-400 border border-green-500/30',
    red: 'bg-red-500/20 text-red-400 border border-red-500/30',
  }

  return (
    <div className={`glass-card p-5 ${colorClasses[color]}`}>
      <div className="flex justify-between items-start">
        <div>
          <p className="text-sm text-white/50 mb-1">{label}</p>
          <p className="text-2xl font-bold">{value}</p>
        </div>
        <div className="text-xl">{icon}</div>
      </div>
    </div>
  )
}
