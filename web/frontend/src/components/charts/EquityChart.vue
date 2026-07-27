<script setup lang="ts">
import { computed } from 'vue'
import BaseChart from './BaseChart.vue'
import type { EChartsOption } from '@/utils/echarts'
import type { CurveSeries } from '@/types/backtest'

const props = defineProps<{ curve: CurveSeries }>()

// 上栏：账户累计收益 vs 上证基准；下栏：回撤（填充）。两栏共享 x 轴与 dataZoom。
const option = computed<EChartsOption>(() => {
  const c = props.curve
  const legend = ['账户累计收益率']
  const series: Record<string, unknown>[] = [
    {
      name: '账户累计收益率',
      type: 'line',
      data: c.equity_pct,
      showSymbol: false,
      itemStyle: { color: '#22c55e' },
      lineStyle: { width: 1.6, color: '#22c55e' },
      areaStyle: { color: 'rgba(34,197,94,0.12)' },
      xAxisIndex: 0,
      yAxisIndex: 0,
    },
  ]
  if (c.benchmark_pct) {
    legend.push('上证指数')
    series.push({
      name: '上证指数',
      type: 'line',
      data: c.benchmark_pct,
      showSymbol: false,
      itemStyle: { color: '#f59e0b' },
      lineStyle: { width: 1.2, color: '#f59e0b' },
      xAxisIndex: 0,
      yAxisIndex: 0,
    })
  }
  legend.push('回撤')
  series.push({
    name: '回撤',
    type: 'line',
    data: c.drawdown_pct,
    showSymbol: false,
    itemStyle: { color: '#ef4444' },
    lineStyle: { width: 1, color: '#ef4444' },
    areaStyle: { color: 'rgba(239,68,68,0.18)' },
    xAxisIndex: 1,
    yAxisIndex: 1,
  })

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: number | string) => (v == null ? '-' : `${Number(v).toFixed(2)}%`),
    },
    legend: { data: legend, top: 0, textStyle: { color: '#cbd5e1' } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 56, right: 24, top: 40, height: '52%' },
      { left: 56, right: 24, top: '70%', height: '18%' },
    ],
    xAxis: [
      { type: 'category', data: c.dates, boundaryGap: false, gridIndex: 0, axisLabel: { show: false } },
      { type: 'category', data: c.dates, boundaryGap: false, gridIndex: 1 },
    ],
    yAxis: [
      { type: 'value', scale: true, gridIndex: 0, axisLabel: { formatter: '{value}%' }, name: '收益率' },
      { type: 'value', scale: true, gridIndex: 1, axisLabel: { formatter: '{value}%' }, name: '回撤' },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1] },
      { type: 'slider', xAxisIndex: [0, 1], bottom: 0, height: 16 },
    ],
    series,
  }
})
</script>

<template>
  <BaseChart :option="option" height="440px" />
</template>
