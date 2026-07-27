import type { BacktestConfig, StrategyConfig } from '@/types/backtest'

// 回测区间显示：YYYYMMDD-YYYYMMDD。
export function formatPeriod(bt: Pick<BacktestConfig, 'backtest_start_time' | 'backtest_end_time'>): string {
  return `${bt.backtest_start_time}-${bt.backtest_end_time}`
}

// 策略标签显示：module.class。
export function formatStrategyLabel(s: StrategyConfig): string {
  return `${s.strategy_module}.${s.strategy_class}`
}

// 金额千分位显示。
export function formatMoney(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

// 小数转百分比显示（如 0.0238 -> 2.38%）。
export function formatPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return `${(v * 100).toFixed(digits)}%`
}
