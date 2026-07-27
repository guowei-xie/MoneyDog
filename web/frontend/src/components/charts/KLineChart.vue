<script setup lang="ts">
import { computed } from 'vue'
import BaseChart from './BaseChart.vue'
import type { EChartsOption } from '@/utils/echarts'
import type { Bar, TradeMarker } from '@/types/backtest'

const props = defineProps<{ bars: Bar[]; markers?: TradeMarker[]; height?: string }>()

// A 股习惯：红涨绿跌
const UP = '#ef4444'
const DOWN = '#22c55e'

function movingAverage(closes: number[], n: number): (number | null)[] {
  return closes.map((_, i) => {
    if (i < n - 1) return null
    let sum = 0
    for (let j = i - n + 1; j <= i; j++) sum += closes[j]
    return Number((sum / n).toFixed(3))
  })
}

const option = computed<EChartsOption>(() => {
  const bars = props.bars
  const dates = bars.map((b) => b.date)
  const candle = bars.map((b) => [b.open, b.close, b.low, b.high])
  const closes = bars.map((b) => b.close)
  const volumes = bars.map((b) => ({
    value: b.volume,
    itemStyle: { color: b.close >= b.open ? UP : DOWN },
  }))

  // 买卖点标记：定位到 [日期, 价格]
  const markPointData = (props.markers ?? []).map((m) => {
    const buy = m.action === 'buy'
    return {
      name: buy ? '买入' : '卖出',
      coord: [m.date, m.price],
      value: buy ? 'B' : 'S',
      symbol: buy ? 'arrow' : 'pin',
      symbolRotate: buy ? 0 : 180,
      symbolSize: 16,
      itemStyle: { color: buy ? '#ef4444' : '#14b8a6' },
      label: { color: '#fff', fontSize: 10 },
    }
  })

  return {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['K线', 'MA5', 'MA10', 'MA20'], top: 0, textStyle: { color: '#cbd5e1' } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 56, right: 16, top: 36, height: '58%' },
      { left: 56, right: 16, top: '74%', height: '16%' },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, boundaryGap: true },
      { type: 'category', data: dates, gridIndex: 1, boundaryGap: true },
    ],
    yAxis: [
      { type: 'value', scale: true, gridIndex: 0 },
      { type: 'value', scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { show: false } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1] },
      { type: 'slider', xAxisIndex: [0, 1], bottom: 0, height: 16 },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: candle,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN },
        markPoint: { data: markPointData, label: { formatter: (p: { value: string }) => String(p.value) } },
      },
      { name: 'MA5', type: 'line', data: movingAverage(closes, 5), showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#f59e0b' } },
      { name: 'MA10', type: 'line', data: movingAverage(closes, 10), showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#38bdf8' } },
      { name: 'MA20', type: 'line', data: movingAverage(closes, 20), showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#a78bfa' } },
      { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1 },
    ],
  }
})
</script>

<template>
  <BaseChart :option="option" :height="height ?? '440px'" />
</template>
