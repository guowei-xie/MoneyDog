<script setup lang="ts">
import { computed } from 'vue'
import { NGrid, NGi, NStatistic, NEmpty } from 'naive-ui'
import { METRIC_DEFS, formatMetric } from '@/utils/metrics'
import type { MetricsDict } from '@/types/backtest'

const props = defineProps<{ metrics?: MetricsDict | null }>()

// 只展示 metrics 中存在的指标，缺失项跳过（兼容旧记录）。
const items = computed(() => {
  const m = props.metrics
  if (!m) return []
  return METRIC_DEFS.filter((d) => m[d.key] !== undefined && m[d.key] !== null).map((d) => ({
    label: d.label,
    value: formatMetric(m[d.key], d.kind),
  }))
})
</script>

<template>
  <NEmpty v-if="items.length === 0" description="暂无账户指标" />
  <NGrid v-else :cols="'2 s:3 m:4 l:5'" responsive="screen" :x-gap="12" :y-gap="12">
    <NGi v-for="it in items" :key="it.label">
      <NStatistic :label="it.label">{{ it.value }}</NStatistic>
    </NGi>
  </NGrid>
</template>
