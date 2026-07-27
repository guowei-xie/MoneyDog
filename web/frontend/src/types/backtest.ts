// 回测相关类型定义（与后端 web/schemas.py 对齐）。

export interface StrategyInfo {
  module: string
  classes: string[]
}

export interface StrategyConfig {
  strategy_module: string
  strategy_class: string
}

export interface BacktestConfig {
  backtest_start_time: string
  backtest_end_time: string
  initial_amount: number
  commission_rate: number
  min_commission: number
  tax_rate: number
  limit_vol_type: string
  max_vol_rate: number
  max_vol_amount: number
  batch_stock_selection_use_threads: boolean
  batch_stock_selection_threads: number
}

export interface AppConfig {
  strategy: StrategyConfig
  backtest: BacktestConfig
}

export interface RunBacktestRequest {
  strategy: StrategyConfig
  backtest: BacktestConfig
}

export type MetricsDict = Record<string, number | string | null>

export interface RunRecord {
  id: string
  created_at: string
  strategy: StrategyConfig
  backtest: BacktestConfig
  files: Record<string, string>
  metrics?: MetricsDict | null
  summary?: { account?: string[]; stock?: string[] } | null
}

export interface CurveSeries {
  dates: string[]
  equity_pct: number[]
  drawdown_pct: number[]
  position_ratio: number[]
  benchmark_pct: number[] | null
  total_assets: number[]
  initial_amount: number
}

export interface Trade {
  code: string
  open_time: string | null
  open_price: number | null
  close_time: string | null
  close_price: number | null
  net_pct: number | null
  gross_pct: number | null
  closed: boolean
  hold_days: number | null
  commission: number | null
  tax: number | null
  cost: number | null
  remark: string | null
}

export interface PositionRow {
  trade_date: string
  stock_count: number
  stock_cost: number
  stock_value: number
  available_amount: number
  total_assets: number
}

export interface RunStatus {
  running: boolean
  run_id: string | null
  stage: string
  current: number
  total: number
  percent: number
  // 运行态恢复扩展字段（P2 后端补充）
  strategy_label?: string | null
  started_at?: string | null
  backtest_period?: string | null
  last_finished_run_id?: string | null
  last_status?: string | null
}
