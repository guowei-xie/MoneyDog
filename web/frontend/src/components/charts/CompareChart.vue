<script setup lang="ts">
import { computed } from 'vue'
import BaseChart from './BaseChart.vue'
import type { EChartsOption } from '@/utils/echarts'

// 多条累计收益曲线叠加。各回测区间可不同，用时间轴自然对齐。
const props = defineProps<{
  series: { name: string; points: [string, number][] }[]
}>()

const PALETTE = ['#22c55e', '#f59e0b', '#38bdf8', '#a78bfa', '#ef4444', '#14b8a6', '#eab308', '#f472b6']

const option = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis', valueFormatter: (v: number | string) => (v == null ? '-' : `${Number(v).toFixed(2)}%`) },
  legend: { data: props.series.map((s) => s.name), top: 0, textStyle: { color: '#cbd5e1' }, type: 'scroll' },
  grid: { left: 56, right: 24, top: 40, bottom: 56 },
  xAxis: { type: 'time' },
  yAxis: { type: 'value', scale: true, axisLabel: { formatter: '{value}%' }, name: '累计收益率' },
  dataZoom: [
    { type: 'inside' },
    { type: 'slider', bottom: 0, height: 16 },
  ],
  series: props.series.map((s, i) => ({
    name: s.name,
    type: 'line',
    data: s.points,
    showSymbol: false,
    itemStyle: { color: PALETTE[i % PALETTE.length] },
    lineStyle: { width: 1.4, color: PALETTE[i % PALETTE.length] },
  })),
}))
</script>

<template>
  <BaseChart :option="option" height="440px" />
</template>
