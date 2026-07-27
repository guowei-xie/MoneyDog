<script setup lang="ts">
import { h, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NDataTable,
  NButton,
  NSpace,
  useDialog,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import CodeModal from './CodeModal.vue'
import { useHistoryStore } from '@/stores/history'
import { recordUrl } from '@/api/backtests'
import { extractError } from '@/api/client'
import { formatMetric } from '@/utils/metrics'
import { formatPeriod } from '@/utils/format'
import type { RunRecord } from '@/types/backtest'

const history = useHistoryStore()
const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const codeModal = ref<InstanceType<typeof CodeModal> | null>(null)

function metricNum(r: RunRecord, key: string): number | null {
  const v = r.metrics?.[key]
  return typeof v === 'number' ? v : null
}

// 按指标数值排序，缺失值排到最后。
const numSorter = (key: string) => (a: RunRecord, b: RunRecord) =>
  (metricNum(a, key) ?? -Infinity) - (metricNum(b, key) ?? -Infinity)

const columns: DataTableColumns<RunRecord> = [
  { title: '回测 ID', key: 'id', sorter: (a, b) => a.id.localeCompare(b.id), width: 170 },
  { title: '策略', key: 'strategy', render: (r) => r.strategy.strategy_class },
  { title: '区间', key: 'period', render: (r) => formatPeriod(r.backtest) },
  {
    title: '总收益%',
    key: 'profit_rate',
    align: 'right',
    sorter: numSorter('profit_rate'),
    render: (r) => formatMetric(metricNum(r, 'profit_rate'), 'pct'),
  },
  {
    title: '最大回撤%',
    key: 'max_drawdown',
    align: 'right',
    sorter: numSorter('max_drawdown'),
    render: (r) => formatMetric(metricNum(r, 'max_drawdown'), 'pct'),
  },
  {
    title: '夏普',
    key: 'sharpe_ratio',
    align: 'right',
    sorter: numSorter('sharpe_ratio'),
    render: (r) => formatMetric(metricNum(r, 'sharpe_ratio'), 'num'),
  },
  {
    title: '操作',
    key: 'actions',
    align: 'right',
    width: 220,
    render: (r) =>
      h(NSpace, { justify: 'end', size: 6, wrap: false }, () => [
        h(NButton, { size: 'tiny', onClick: () => router.push(`/runs/${r.id}`) }, () => '查看'),
        h(NButton, { size: 'tiny', onClick: () => codeModal.value?.open(r.id, r.strategy.strategy_class) }, () => '代码'),
        h(NButton, { size: 'tiny', tag: 'a', href: recordUrl(r.id), target: '_blank' }, () => '记录'),
        h(NButton, { size: 'tiny', type: 'error', ghost: true, onClick: () => confirmDelete(r) }, () => '删除'),
      ]),
  },
]

function confirmDelete(r: RunRecord) {
  dialog.warning({
    title: '删除回测记录',
    content: `确定删除 ${r.id} 吗？仅移除记录，不会删除结果文件。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await history.remove(r.id)
        message.success(`已删除记录 ${r.id}`)
      } catch (err) {
        message.error(extractError(err))
      }
    },
  })
}
</script>

<template>
  <div>
    <NDataTable
      :columns="columns"
      :data="history.sorted"
      :loading="history.loading"
      :row-key="(r: RunRecord) => r.id"
      :pagination="{ pageSize: 10 }"
      size="small"
    />
    <CodeModal ref="codeModal" />
  </div>
</template>
