// ECharts 按需引入：只注册用到的图表与组件，控制打包体积。
import * as echarts from 'echarts/core'
import { LineChart, CandlestickChart, BarChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkPointComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  CandlestickChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkPointComponent,
  CanvasRenderer,
])

export { echarts }
export type EChartsOption = echarts.EChartsCoreOption

// 折线 tooltip 的百分比格式化（收益率类曲线共用，值为已放大的百分数）。
export const pctPointFormatter = (v: number | string): string =>
  v == null ? '-' : `${Number(v).toFixed(2)}%`
