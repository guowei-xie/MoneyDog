<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard,
  NGrid,
  NGi,
  NStatistic,
  NSpin,
  NEmpty,
  NTag,
  NButton,
  NSpace,
  NText,
  NDataTable,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { getDashboard } from '@/api/dashboard'
import { extractError } from '@/api/client'
import { formatMetric } from '@/utils/metrics'
import { linkCell } from '@/utils/table'
import type { DashboardSummary, RunBrief } from '@/types/dashboard'

const message = useMessage()
const router = useRouter()
const loading = ref(true)
const data = ref<DashboardSummary | null>(null)

onMounted(async () => {
  try {
    data.value = await getDashboard()
  } catch (err) {
    message.error(extractError(err))
  } finally {
    loading.value = false
  }
})

const recentColumns: DataTableColumns<RunBrief> = [
  {
    title: '回测 ID',
    key: 'id',
    render: (r) => linkCell(r.id, () => router.push(`/runs/${r.id}`)),
  },
  { title: '策略', key: 'strategy_label', render: (r) => r.strategy_label.split('.').pop() },
  { title: '总收益%', key: 'profit_rate', align: 'right', render: (r) => formatMetric(r.profit_rate, 'pct') },
  { title: '最大回撤%', key: 'max_drawdown', align: 'right', render: (r) => formatMetric(r.max_drawdown, 'pct') },
  { title: '夏普', key: 'sharpe_ratio', align: 'right', render: (r) => formatMetric(r.sharpe_ratio, 'num') },
]
</script>

<template>
  <NSpin :show="loading">
    <NEmpty v-if="!data && !loading" description="暂无数据" />
    <NSpace v-else-if="data" vertical :size="16">
      <NGrid :cols="'2 s:4'" responsive="screen" :x-gap="12" :y-gap="12">
        <NGi>
          <NCard><NStatistic label="回测总数" :value="data.total_runs" /></NCard>
        </NGi>
        <NGi>
          <NCard>
            <NStatistic label="运行状态">
              <NTag v-if="data.running" type="success" size="small" round>运行中</NTag>
              <NText v-else depth="3">空闲</NText>
            </NStatistic>
          </NCard>
        </NGi>
        <NGi>
          <NCard><NStatistic label="股票池数量" :value="data.data.stock_count" /></NCard>
        </NGi>
        <NGi>
          <NCard>
            <NStatistic label="数据交易日" :value="data.data.trade_days" />
            <NText depth="3" style="font-size: 11px">
              {{ data.data.daily_start ?? '-' }} ~ {{ data.data.daily_end ?? '-' }}
            </NText>
          </NCard>
        </NGi>
      </NGrid>

      <NCard v-if="data.best_by_sharpe" title="最优回测（按夏普）">
        <NSpace align="center" justify="space-between">
          <div>
            <NText strong>{{ data.best_by_sharpe.strategy_label }}</NText>
            <NText depth="3" style="margin-left: 8px">{{ data.best_by_sharpe.id }}</NText>
            <div style="margin-top: 6px">
              <NText depth="3">夏普 {{ formatMetric(data.best_by_sharpe.sharpe_ratio, 'num') }} ·</NText>
              <NText depth="3"> 收益 {{ formatMetric(data.best_by_sharpe.profit_rate, 'pct') }} ·</NText>
              <NText depth="3"> 回撤 {{ formatMetric(data.best_by_sharpe.max_drawdown, 'pct') }}</NText>
            </div>
          </div>
          <NButton size="small" @click="router.push(`/runs/${data.best_by_sharpe.id}`)">查看</NButton>
        </NSpace>
      </NCard>

      <NCard title="最近回测">
        <template #header-extra>
          <NSpace>
            <NButton size="small" type="primary" @click="router.push('/run')">新建回测</NButton>
            <NButton size="small" @click="router.push('/compare')">策略对比</NButton>
          </NSpace>
        </template>
        <NEmpty v-if="data.recent.length === 0" description="暂无回测记录" />
        <NDataTable
          v-else
          :columns="recentColumns"
          :data="data.recent"
          :row-key="(r: RunBrief) => r.id"
          size="small"
          :pagination="false"
        />
      </NCard>
    </NSpace>
  </NSpin>
</template>
