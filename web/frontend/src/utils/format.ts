import type { BacktestConfig, StrategyConfig } from '@/types/backtest'

// 回测区间显示：YYYYMMDD-YYYYMMDD。
export function formatPeriod(bt: Pick<BacktestConfig, 'backtest_start_time' | 'backtest_end_time'>): string {
  return `${bt.backtest_start_time}-${bt.backtest_end_time}`
}

// 策略标签显示：module.class。
export function formatStrategyLabel(s: StrategyConfig): string {
  return `${s.strategy_module}.${s.strategy_class}`
}
