import client from './client'
import type {
  AppConfig,
  CurveSeries,
  RunBacktestRequest,
  RunRecord,
  RunStatus,
  StrategyInfo,
  MetricsDict,
} from '@/types/backtest'

export async function getStrategies(): Promise<StrategyInfo[]> {
  const { data } = await client.get<StrategyInfo[]>('/strategies')
  return data
}

export async function getConfig(): Promise<AppConfig> {
  const { data } = await client.get<AppConfig>('/config')
  return data
}

export async function runBacktest(payload: RunBacktestRequest): Promise<{ run_id: string; status: string }> {
  const { data } = await client.post('/backtests/run', payload)
  return data
}

export async function listBacktests(): Promise<RunRecord[]> {
  const { data } = await client.get<RunRecord[]>('/backtests')
  return data
}

export async function getBacktest(runId: string): Promise<RunRecord> {
  const { data } = await client.get<RunRecord>(`/backtests/${encodeURIComponent(runId)}`)
  return data
}

export async function getStatus(): Promise<RunStatus> {
  const { data } = await client.get<RunStatus>('/backtests/status')
  return data
}

export async function stopBacktest(): Promise<{ success: boolean; run_id: string }> {
  const { data } = await client.post('/backtests/stop')
  return data
}

export async function deleteBacktest(runId: string): Promise<{ success: boolean; run_id: string }> {
  const { data } = await client.delete(`/backtests/${encodeURIComponent(runId)}`)
  return data
}

export async function getMetrics(runId: string): Promise<MetricsDict> {
  const { data } = await client.get<MetricsDict>(`/backtests/${encodeURIComponent(runId)}/metrics`)
  return data
}

export async function getCurve(runId: string): Promise<CurveSeries> {
  const { data } = await client.get<CurveSeries>(`/backtests/${encodeURIComponent(runId)}/curve.json`)
  return data
}

export async function getCode(runId: string): Promise<{ file_name: string; code: string }> {
  const { data } = await client.get(`/backtests/${encodeURIComponent(runId)}/code`)
  return data
}

// 记录 Excel 下载直链（在新标签打开）。
export function recordUrl(runId: string): string {
  return `/api/backtests/${encodeURIComponent(runId)}/record`
}
