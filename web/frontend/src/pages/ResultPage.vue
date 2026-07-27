<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { NCard, NSpace, NButton, NSpin, NAlert, NEmpty, NText, NTabs, NTabPane } from 'naive-ui'
import MetricsCards from '@/components/MetricsCards.vue'
import CodeModal from '@/components/CodeModal.vue'
import EquityChart from '@/components/charts/EquityChart.vue'
import PositionChart from '@/components/charts/PositionChart.vue'
import TradesTable from '@/components/TradesTable.vue'
import PositionsTable from '@/components/PositionsTable.vue'
import KlineModal from '@/components/KlineModal.vue'
import { useHistoryStore } from '@/stores/history'
import { getBacktest, getCurve, getMetrics, getTrades, getPositions, recordUrl } from '@/api/backtests'
import { extractError } from '@/api/client'
import { formatPeriod, formatStrategyLabel } from '@/utils/format'
import type { CurveSeries, MetricsDict, PositionRow, RunRecord, Trade } from '@/types/backtest'

const route = useRoute()
const history = useHistoryStore()
const runId = computed(() => String(route.params.id))

const loading = ref(true)
const errorMsg = ref('')
const record = ref<RunRecord | null>(null)
const metrics = ref<MetricsDict | null>(null)
const curve = ref<CurveSeries | null>(null)
const trades = ref<Trade[]>([])
const positions = ref<PositionRow[]>([])
const codeModal = ref<InstanceType<typeof CodeModal> | null>(null)
const klineModal = ref<InstanceType<typeof KlineModal> | null>(null)

async function load() {
  loading.value = true
  errorMsg.value = ''
  curve.value = null
  trades.value = []
  positions.value = []
  try {
    // 命中历史缓存则复用，否则按 id 精确拉取单条记录（深链/刷新场景）。
    record.value = history.find(runId.value) ?? (await getBacktest(runId.value))
    metrics.value = record.value.metrics ?? (await getMetrics(runId.value))
    // 曲线/交易/持仓独立获取，任一失败不阻断其余展示。
    try {
      curve.value = await getCurve(runId.value)
    } catch {
      curve.value = null
    }
    try {
      trades.value = await getTrades(runId.value)
    } catch {
      trades.value = []
    }
    try {
      positions.value = await getPositions(runId.value)
    } catch {
      positions.value = []
    }
  } catch (err) {
    errorMsg.value = extractError(err)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <NSpin :show="loading">
    <NAlert v-if="errorMsg" type="error" title="加载失败">{{ errorMsg }}</NAlert>
    <NSpace v-else vertical :size="16">
      <NCard :title="`回测结果 · ${runId}`">
        <template #header-extra>
          <NSpace>
            <NButton
              size="small"
              @click="codeModal?.open(runId, record?.strategy.strategy_class ?? '')"
            >
              查看策略代码
            </NButton>
            <NButton size="small" tag="a" :href="recordUrl(runId)" target="_blank">下载记录 Excel</NButton>
          </NSpace>
        </template>
        <NText v-if="record" depth="3">
          {{ formatStrategyLabel(record.strategy) }} · {{ formatPeriod(record.backtest) }} ·
          {{ record.created_at }}
        </NText>
        <div style="margin-top: 16px">
          <MetricsCards :metrics="metrics" />
        </div>
      </NCard>

      <NCard title="账户收益与回撤">
        <EquityChart v-if="curve" :curve="curve" />
        <NEmpty v-else description="暂无曲线数据" />
      </NCard>

      <NCard title="仓位变化" v-if="curve">
        <PositionChart :curve="curve" />
      </NCard>

      <NCard title="分析摘要">
        <NSpace :size="24" style="width: 100%" :wrap="true">
          <div style="flex: 1; min-width: 280px">
            <NText depth="3" style="font-size: 12px">账户分析</NText>
            <pre class="summary-pre">{{ (record?.summary?.account ?? []).join('\n') || '暂无账户分析摘要。' }}</pre>
          </div>
          <div style="flex: 1; min-width: 280px">
            <NText depth="3" style="font-size: 12px">个股分析</NText>
            <pre class="summary-pre">{{ (record?.summary?.stock ?? []).join('\n') || '暂无个股分析摘要。' }}</pre>
          </div>
        </NSpace>
      </NCard>

      <NCard title="交易与持仓明细">
        <NTabs type="line" animated>
          <NTabPane name="trades" :tab="`交易明细 (${trades.length})`">
            <TradesTable :trades="trades" @drill="(code) => klineModal?.open(runId, code)" />
          </NTabPane>
          <NTabPane name="positions" :tab="`持仓时间线 (${positions.length})`">
            <PositionsTable :positions="positions" />
          </NTabPane>
        </NTabs>
      </NCard>

      <NEmpty v-if="!record" description="无数据" />
    </NSpace>
    <CodeModal ref="codeModal" />
    <KlineModal ref="klineModal" />
  </NSpin>
</template>

<style scoped>
.summary-pre {
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  margin-top: 6px;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
</style>
