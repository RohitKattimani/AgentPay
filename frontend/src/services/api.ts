import axios, { AxiosInstance } from 'axios'

const API_BASE_URL = '/api'
const ACTIVE_TASK_KEY = 'agentpay.activeTaskId'

export function setActiveTaskId(taskId: number) {
  if (typeof window !== 'undefined') window.localStorage.setItem(ACTIVE_TASK_KEY, String(taskId))
}

export function getActiveTaskId(): number | null {
  if (typeof window === 'undefined') return null
  const value = Number(window.localStorage.getItem(ACTIVE_TASK_KEY))
  return Number.isInteger(value) && value > 0 ? value : null
}

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface Task {
  id: number
  task_id?: number
  title: string
  description: string
  status: string
  budget: number
  currency: string
  deadline_minutes: number
  deliverables?: string
  acceptance_criteria?: string
  csv_file_path?: string
  created_at?: string
}

export interface Bid {
  id: number
  seller_name: string
  price: number
  delivery_minutes: number
  rating: number
  score?: number
  is_winner: boolean
}

export interface Contract {
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

export interface VerificationReport {
  id: number
  task_id: number
  missing_values: number
  duplicate_records: number
  invalid_emails: number
  formatting_errors: number
  verification_status: string
  report_text: string
  revision_count: number
  created_at?: string
}

export interface Payment {
  id: number
  task_id: number
  task_name: string
  seller: string
  amount: number
  verification_status: string
  payment_status: string
  paypal_order_id?: string
  paypal_capture_id?: string
  created_at?: string
}

export interface AgentInfo {
  name: string
  status: string
  last_activity: string
  last_activity_time?: string
  event_count: number
}

export interface DashboardStats {
  total_tasks: number
  active_tasks: number
  completed_tasks: number
  failed_tasks: number
  total_volume: number
  recent_activity: Array<{
    agent: string
    event: string
    task_id?: number
    time?: string
  }>
}

export const taskApi = {
  list: () => api.get<Task[]>('/tasks'),
  get: (id: number) => api.get<Task>(`/tasks/${id}`),
  create: (data: { description: string; budget?: number; file?: File }) => {
    const formData = new FormData()
    formData.append('description', data.description)
    if (data.budget !== undefined) formData.append('budget', String(data.budget))
    if (data.file) formData.append('file', data.file)
    return api.post<Task>('/tasks', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  start: (id: number) => api.post(`/tasks/${id}/start`),
  execute: (id: number) => api.post(`/tasks/${id}/execute`),
}

export const negotiationApi = {
  start: (taskId: number) => api.post(`/negotiations/${taskId}/start`),
  getBids: (taskId: number) => api.get<Bid[]>(`/negotiations/${taskId}/bids`),
}

export const contractApi = {
  get: (taskId: number) => api.get<Contract>(`/contracts/${taskId}`),
  approve: (taskId: number) => api.post(`/contracts/${taskId}/approve`),
  reject: (taskId: number) => api.post(`/contracts/${taskId}/reject`),
}

export const verificationApi = {
  run: (taskId: number) => api.post(`/verification/${taskId}/run`),
  get: (taskId: number) => api.get<VerificationReport>(`/verification/${taskId}`),
}

export const paymentApi = {
  authorize: (taskId: number) => api.post(`/payments/${taskId}/authorize`),
  completeAuthorization: (taskId: number, orderId: string) =>
    api.post(`/payments/${taskId}/complete-authorization`, { order_id: orderId }),
  list: () => api.get<Payment[]>('/transactions'),
}

export const agentsApi = {
  list: () => api.get<AgentInfo[]>('/agents'),
}

export const statsApi = {
  get: () => api.get<DashboardStats>('/dashboard/stats'),
}
