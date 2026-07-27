import client from './client'
import type { Bar } from '@/types/backtest'
import type { CoverageInfo, IndexInfo, StockInfo } from '@/types/market'

export async function listStocks(q = '', limit = 50): Promise<{ stocks: StockInfo[]; total: number }> {
  const { data } = await client.get('/market/stocks', { params: { q, limit } })
  return data
}

export async function listIndices(): Promise<IndexInfo[]> {
  const { data } = await client.get<{ indices: IndexInfo[] }>('/market/indices')
  return data.indices
}

export async function getCoverage(code: string, market: 'stock' | 'index'): Promise<CoverageInfo> {
  const { data } = await client.get<CoverageInfo>('/market/coverage', { params: { code, market } })
  return data
}

export async function getMarketBars(
  code: string,
  period: '1d' | '1m',
  start: string,
  end: string,
  market: 'stock' | 'index',
): Promise<{ code: string; period: string; bars: Bar[] }> {
  const { data } = await client.get('/market/bars', { params: { code, period, start, end, market } })
  return data
}
