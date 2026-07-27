<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  NCard,
  NSpace,
  NRadioGroup,
  NRadioButton,
  NSelect,
  NDatePicker,
  NButton,
  NSpin,
  NEmpty,
  NText,
  NDescriptions,
  NDescriptionsItem,
  useMessage,
  type SelectOption,
} from 'naive-ui'
import KLineChart from '@/components/charts/KLineChart.vue'
import { listStocks, listIndices, getCoverage, getMarketBars } from '@/api/market'
import { extractError } from '@/api/client'
import type { Bar } from '@/types/backtest'
import type { CoverageInfo } from '@/types/market'

const message = useMessage()

const market = ref<'stock' | 'index'>('stock')
const period = ref<'1d' | '1m'>('1d')
const code = ref<string | null>(null)
const dateRange = ref<[string, string] | null>(null)
const singleDay = ref<string | null>(null)

const stockOptions = ref<SelectOption[]>([])
const indexOptions = ref<SelectOption[]>([])
const searching = ref(false)

const bars = ref<Bar[]>([])
const coverage = ref<CoverageInfo | null>(null)
const loading = ref(false)

const codeOptions = computed(() => (market.value === 'stock' ? stockOptions.value : indexOptions.value))

async function handleSearch(q: string) {
  if (market.value !== 'stock') return
  searching.value = true
  try {
    const { stocks } = await listStocks(q, 50)
    stockOptions.value = stocks.map((s) => ({ label: s.code, value: s.code }))
  } catch (err) {
    message.error(extractError(err))
  } finally {
    searching.value = false
  }
}

// 切换市场类型时重置代码与选项。
watch(market, async () => {
  code.value = null
  bars.value = []
  coverage.value = null
  if (market.value === 'stock') {
    handleSearch('')
  } else {
    // 指数仅有日线
    period.value = '1d'
  }
})

onMounted(async () => {
  handleSearch('')
  try {
    const indices = await listIndices()
    indexOptions.value = indices.map((i) => ({ label: `${i.name} (${i.code})`, value: i.code }))
  } catch (err) {
    message.error(extractError(err))
  }
})

async function handleLoad() {
  if (!code.value) {
    message.warning('请选择代码')
    return
  }
  let start = ''
  let end = ''
  if (period.value === '1m') {
    if (!singleDay.value) {
      message.warning('分钟线请选择单个交易日')
      return
    }
    start = end = singleDay.value
  } else {
    if (!dateRange.value) {
      message.warning('请选择日期区间')
      return
    }
    ;[start, end] = dateRange.value
  }
  loading.value = true
  bars.value = []
  try {
    const [barsResp, cov] = await Promise.all([
      getMarketBars(code.value, period.value, start, end, market.value),
      getCoverage(code.value, market.value),
    ])
    bars.value = barsResp.bars
    coverage.value = cov
    if (barsResp.bars.length === 0) message.info('该区间无行情数据')
  } catch (err) {
    message.error(extractError(err))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <NSpace vertical :size="16">
    <NCard title="行情浏览">
      <NSpace vertical :size="14">
        <NSpace align="center" :wrap="true">
          <NRadioGroup v-model:value="market">
            <NRadioButton value="stock">个股</NRadioButton>
            <NRadioButton value="index">指数</NRadioButton>
          </NRadioGroup>
          <NSelect
            v-model:value="code"
            :options="codeOptions"
            filterable
            :remote="market === 'stock'"
            :loading="searching"
            placeholder="选择/搜索代码"
            style="width: 240px"
            @search="handleSearch"
          />
          <NRadioGroup v-model:value="period" v-if="market === 'stock'">
            <NRadioButton value="1d">日线</NRadioButton>
            <NRadioButton value="1m">分钟线</NRadioButton>
          </NRadioGroup>
          <NDatePicker
            v-if="period === '1d'"
            v-model:formatted-value="dateRange"
            type="daterange"
            value-format="yyyyMMdd"
            clearable
          />
          <NDatePicker
            v-else
            v-model:formatted-value="singleDay"
            type="date"
            value-format="yyyyMMdd"
            clearable
            placeholder="选择单个交易日"
          />
          <NButton type="primary" :loading="loading" @click="handleLoad">加载</NButton>
        </NSpace>

        <NDescriptions v-if="coverage" :column="3" size="small" bordered label-placement="left">
          <NDescriptionsItem label="日线覆盖">
            {{ coverage.daily.start ?? '-' }} ~ {{ coverage.daily.end ?? '-' }}（{{ coverage.daily.count }} 条）
          </NDescriptionsItem>
          <NDescriptionsItem label="分钟线覆盖">
            <template v-if="coverage.minute">
              {{ coverage.minute.start ?? '-' }} ~ {{ coverage.minute.end ?? '-' }}（{{ coverage.minute.count }} 条）
            </template>
            <template v-else>—</template>
          </NDescriptionsItem>
        </NDescriptions>
        <NText v-if="market === 'stock'" depth="3" style="font-size: 12px">
          注：数据源仅含股票代码，无中文名称。
        </NText>
      </NSpace>
    </NCard>

    <NCard title="K 线">
      <NSpin :show="loading">
        <NEmpty v-if="bars.length === 0" description="选择代码与区间后点击加载" />
        <KLineChart v-else :bars="bars" height="500px" />
      </NSpin>
    </NCard>
  </NSpace>
</template>
