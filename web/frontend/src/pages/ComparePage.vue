<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import {
  NCard,
  NSelect,
  NSpace,
  NSpin,
  NEmpty,
  NText,
  NDataTable,
  useMessage,
  type SelectOption,
  type DataTableColumns,
} from 'naive-ui'
import CompareChart from '@/components/charts/CompareChart.vue'
import { useHistoryStore } from '@/stores/history'
import { useCompareStore, type CompareEntry } from '@/stores/compare'
import { extractError } from '@/api/client'
import { formatMetric, pickMetrics } from '@/utils/metrics'
import { formatPeriod } from '@/utils/format'

const message = useMessage()
const history = useHistoryStore()
const compare = useCompareStore()

const selectedIds = ref<string[]>([])

const runOptions = computed<SelectOption[]>(() =>
  history.sorted.map((r) => ({ label: `${r.id} · ${r.strategy.strategy_class}`, value: r.id })),
)

onMounted(() => history.load().catch((err) => message.error(extractError(err))))

watch(selectedIds, async (ids) => {
  if (ids.length === 0) {
    compare.clear()
    return
  }
  try {
    await compare.load(ids)
  } catch (err) {
    message.error(extractError(err))
  }
})

// 叠加曲线：每个回测一条累计收益率线（时间轴对齐）。
const chartSeries = computed(() =>
  compare.entries.map((e) => ({
    name: `${e.id} · ${e.record.strategy.strategy_class}`,
    points: e.curve.dates.map((d, i) => [d, e.curve.equity_pct[i]] as [string, number]),
  })),
)

// 指标对照表：每行一个回测。列定义复用 METRIC_DEFS 的 label/kind。
const metricCols = pickMetrics([
  'profit_rate',
  'annual_return',
  'max_drawdown',
  'sharpe_ratio',
  'calmar_ratio',
  'max_position_rate',
])

const tableColumns = computed<DataTableColumns<CompareEntry>>(() => [
  { title: '回测', key: 'id', render: (e) => `${e.id} · ${e.record.strategy.strategy_class}` },
  { title: '区间', key: 'period', render: (e) => formatPeriod(e.record.backtest) },
  ...metricCols.map((m) => ({
    title: m.label,
    key: m.key,
    align: 'right' as const,
    render: (e: CompareEntry) => h('span', formatMetric(e.record.metrics?.[m.key], m.kind)),
  })),
])
</script>

<template>
  <NSpace vertical :size="16">
    <NCard title="策略对比">
      <NSpace vertical :size="12">
        <NSelect
          v-model:value="selectedIds"
          multiple
          filterable
          :options="runOptions"
          placeholder="选择多个回测进行对比"
          :max-tag-count="6"
        />
        <NText depth="3" style="font-size: 12px">选择 2 个及以上回测，叠加累计收益曲线并对照关键指标。</NText>
      </NSpace>
    </NCard>

    <NCard title="累计收益曲线对比">
      <NSpin :show="compare.loading">
        <NEmpty v-if="chartSeries.length === 0" description="请选择回测" />
        <CompareChart v-else :series="chartSeries" />
      </NSpin>
    </NCard>

    <NCard title="指标对照">
      <NEmpty v-if="compare.entries.length === 0" description="请选择回测" />
      <NDataTable
        v-else
        :columns="tableColumns"
        :data="compare.entries"
        :row-key="(e: CompareEntry) => e.id"
        size="small"
      />
    </NCard>
  </NSpace>
</template>
