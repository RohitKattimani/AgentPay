import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import CreateTask from './pages/CreateTask'
import NegotiationCenter from './pages/NegotiationCenter'
import ContractApproval from './pages/ContractApproval'
import VerificationCenter from './pages/VerificationCenter'
import Transactions from './pages/Transactions'
import AgentMonitoring from './pages/AgentMonitoring'
import PaymentReturn from './pages/PaymentReturn'

const navItems = [
  { path: '/', label: 'Dashboard', icon: 'LayoutDashboard' },
  { path: '/create', label: 'Create Task', icon: 'FilePlus' },
  { path: '/negotiation', label: 'Negotiation', icon: 'Share2' },
  { path: '/contract', label: 'Contract Approval', icon: 'FileSignature' },
  { path: '/verification', label: 'Verification', icon: 'ShieldCheck' },
  { path: '/transactions', label: 'Transactions', icon: 'CreditCard' },
  { path: '/agents', label: 'Agent Monitoring', icon: 'Bot' },
]

export default function App() {

  return (
    <Router>
      <div className="min-h-screen flex">
        <nav className="w-64 bg-navy-900 border-r border-white/10 flex flex-col h-screen fixed">
          <div className="p-6">
            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-violet-500 bg-clip-text text-transparent">AgentPay</h1>
            <p className="text-xs text-white/40 mt-1">Autonomous task marketplace</p>
          </div>
          <div className="flex-1 overflow-y-auto py-4">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center px-6 py-3 text-white/60 hover:bg-white/10 hover:text-white transition-colors ${
                    isActive ? 'bg-blue-500/20 text-white border-r-2 border-blue-500' : ''
                  }`
                }
              >
                <span className="mr-3">{getIcon(item.icon)}</span>
                {item.label}
              </NavLink>
            ))}
          </div>
          <div className="p-6 border-t border-white/10">
            <div className="glass-card p-4">
              <p className="text-xs text-white/40 mb-1">Workspace</p>
              <p className="text-xs text-white/70">Local development environment</p>
            </div>
          </div>
        </nav>
        <div className="flex-1 pl-64">
          <main className="p-6">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/create" element={<CreateTask />} />
              <Route path="/negotiation" element={<NegotiationCenter />} />
              <Route path="/contract" element={<ContractApproval />} />
              <Route path="/verification" element={<VerificationCenter />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/agents" element={<AgentMonitoring />} />
              <Route path="/payment/return" element={<PaymentReturn />} />
            </Routes>
          </main>
        </div>
      </div>
    </Router>
  )
}

function getIcon(name: string) {
  const icons: Record<string, string> = {
    LayoutDashboard: '📊',
    FilePlus: '➕',
    Share2: '🤝',
    FileSignature: '📄',
    ShieldCheck: '✅',
    CreditCard: '💳',
    Bot: '🤖',
  }
  return icons[name] || '•'
}
