import client from './client'
import type { DashboardSummary } from '@/types/dashboard'

export async function getDashboard(): Promise<DashboardSummary> {
  const { data } = await client.get<DashboardSummary>('/dashboard')
  return data
}
