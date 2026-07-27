<script setup lang="ts">
import { computed } from 'vue'
import BaseChart from './BaseChart.vue'
import type { EChartsOption } from '@/utils/echarts'
import type { CurveSeries } from '@/types/backtest'

const props = defineProps<{ curve: CurveSeries }>()

// 仓位比例（持仓价值/总资产）随时间变化的填充折线。
const option = computed<EChartsOption>(() => {
  const c = props.curve
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: number | string) => (v == null ? '-' : `${(Number(v) * 100).toFixed(2)}%`),
    },
    grid: { left: 56, right: 24, top: 24, bottom: 40 },
    xAxis: { type: 'category', data: c.dates, boundaryGap: false },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
    },
    dataZoom: [
      { type: 'inside' },
      { type: 'slider', bottom: 0, height: 16 },
    ],
    series: [
      {
        name: '仓位比例',
        type: 'line',
        data: c.position_ratio,
        showSymbol: false,
        lineStyle: { width: 1.4, color: '#38bdf8' },
        areaStyle: { color: 'rgba(56,189,248,0.15)' },
      },
    ],
  }
})
</script>

<template>
  <BaseChart :option="option" height="260px" />
</template>
