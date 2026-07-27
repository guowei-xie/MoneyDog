// 指标展示定义：label 中文名、kind 决定格式化方式（pct 表示后端存的是小数，展示为百分比）。
// 这是后端 _build_account_summary 指标口径在前端的镜像，新增/改名指标时需与后端保持一致。
export interface MetricDef {
  key: string
  label: string
  kind: 'pct' | 'num' | 'int'
}

// 卡片展示的核心指标（覆盖后端计算的主要 ~13 项）。
export const METRIC_DEFS: MetricDef[] = [
  { key: 'profit_rate', label: '总收益率', kind: 'pct' },
  { key: 'annual_return', label: '年化收益率', kind: 'pct' },
  { key: 'max_drawdown', label: '最大回撤', kind: 'pct' },
  { key: 'annual_volatility', label: '年化波动率', kind: 'pct' },
  { key: 'sharpe_ratio', label: '夏普比率', kind: 'num' },
  { key: 'sortino_ratio', label: '索提诺比率', kind: 'num' },
  { key: 'calmar_ratio', label: '卡玛比率', kind: 'num' },
  { key: 'excess_return', label: '超额年化(相对上证)', kind: 'pct' },
  { key: 'beta', label: 'Beta', kind: 'num' },
  { key: 'alpha', label: 'Alpha(年化)', kind: 'pct' },
  { key: 'max_profit_rate', label: '最大涨幅', kind: 'pct' },
  { key: 'max_loss_rate', label: '最大跌幅', kind: 'pct' },
  { key: 'max_position_rate', label: '最大仓位', kind: 'pct' },
  { key: 'max_stock_count', label: '最大持仓数', kind: 'int' },
  { key: 'empty_days', label: '空仓天数', kind: 'int' },
]

// 按 key 顺序从 METRIC_DEFS 中挑选指标定义（供对比表等复用统一的 label/kind）。
export function pickMetrics(keys: string[]): MetricDef[] {
  return keys
    .map((k) => METRIC_DEFS.find((d) => d.key === k))
    .filter((d): d is MetricDef => d !== undefined)
}

export function formatMetric(value: number | string | null | undefined, kind: MetricDef['kind']): string {
  if (value === null || value === undefined || value === '') return '-'
  const num = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(num)) return String(value)
  switch (kind) {
    case 'pct':
      return (num * 100).toFixed(2) + '%'
    case 'num':
      return num.toFixed(2)
    case 'int':
      return String(Math.round(num))
    default:
      return String(num)
  }
}
