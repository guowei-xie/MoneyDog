export interface RunBrief {
  id: string
  created_at: string
  strategy_label: string
  profit_rate: number | null
  max_drawdown: number | null
  sharpe_ratio: number | null
}

export interface DashboardSummary {
  total_runs: number
  running: boolean
  active_run_id: string | null
  recent: RunBrief[]
  best_by_sharpe: RunBrief | null
  data: {
    stock_count: number
    daily_start: string | null
    daily_end: string | null
    trade_days: number
  }
}
