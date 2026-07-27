<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard,
  NForm,
  NFormItem,
  NGrid,
  NGi,
  NSelect,
  NDatePicker,
  NInputNumber,
  NSwitch,
  NButton,
  NSpace,
  NText,
  useMessage,
  type SelectOption,
} from 'naive-ui'
import { getStrategies, getConfig } from '@/api/backtests'
import { extractError } from '@/api/client'
import { useRunStore } from '@/stores/run'
import { useHistoryStore } from '@/stores/history'
import RunProgress from '@/components/RunProgress.vue'
import HistoryTable from '@/components/HistoryTable.vue'
import type { StrategyInfo } from '@/types/backtest'

const message = useMessage()
const router = useRouter()
const run = useRunStore()
const history = useHistoryStore()

const strategies = ref<StrategyInfo[]>([])
const loading = ref(true)

const form = reactive({
  strategy_module: '',
  strategy_class: '',
  dateRange: null as [string, string] | null,
  initial_amount: 100000,
  commission_rate: 0.0001,
  min_commission: 5,
  tax_rate: 0.0005,
  limit_vol_type: 'ratio',
  max_vol_rate: 0.05,
  max_vol_amount: 100000,
  batch_use_threads: true,
  batch_threads: 0,
})

const moduleOptions = computed<SelectOption[]>(() =>
  strategies.value.map((s) => ({ label: s.module, value: s.module })),
)
const classOptions = computed<SelectOption[]>(() => {
  const item = strategies.value.find((s) => s.module === form.strategy_module)
  return (item?.classes ?? []).map((c) => ({ label: c, value: c }))
})

// 切换模块后，若当前类不在新模块下，自动选中首个类。
watch(
  () => form.strategy_module,
  () => {
    const classes = classOptions.value.map((o) => o.value)
    if (!classes.includes(form.strategy_class)) {
      form.strategy_class = (classes[0] as string) ?? ''
    }
  },
)

onMounted(async () => {
  try {
    const [s, c] = await Promise.all([getStrategies(), getConfig()])
    strategies.value = s
    form.strategy_module = c.strategy.strategy_module
    form.strategy_class = c.strategy.strategy_class
    const b = c.backtest
    form.dateRange = [b.backtest_start_time, b.backtest_end_time]
    form.initial_amount = b.initial_amount
    form.commission_rate = b.commission_rate
    form.min_commission = b.min_commission
    form.tax_rate = b.tax_rate
    form.limit_vol_type = b.limit_vol_type || 'ratio'
    form.max_vol_rate = b.max_vol_rate
    form.max_vol_amount = b.max_vol_amount
    form.batch_use_threads = b.batch_stock_selection_use_threads
    form.batch_threads = b.batch_stock_selection_threads
  } catch (err) {
    message.error('加载配置失败：' + extractError(err))
  } finally {
    loading.value = false
  }
  history.load().catch((err) => message.error(extractError(err)))
})

// 运行中 -> 结束的跳变：刷新历史并跳转结果页。
watch(
  () => run.running,
  (now, prev) => {
    if (!(prev && !now)) return
    history.load()
    if (run.lastStatus === 'failed') {
      message.error('回测执行失败，请查看服务器日志。')
    } else if (run.lastFinishedRunId) {
      message.success('回测完成')
      router.push(`/runs/${run.lastFinishedRunId}`)
    }
  },
)

async function handleRun() {
  if (!form.strategy_module || !form.strategy_class) {
    message.warning('请选择策略模块与策略类')
    return
  }
  if (!form.dateRange) {
    message.warning('请选择回测时间区间')
    return
  }
  const payload = {
    strategy: { strategy_module: form.strategy_module, strategy_class: form.strategy_class },
    backtest: {
      backtest_start_time: form.dateRange[0],
      backtest_end_time: form.dateRange[1],
      initial_amount: form.initial_amount,
      commission_rate: form.commission_rate,
      min_commission: form.min_commission,
      tax_rate: form.tax_rate,
      limit_vol_type: form.limit_vol_type,
      max_vol_rate: form.max_vol_rate,
      max_vol_amount: form.max_vol_amount,
      batch_stock_selection_use_threads: form.batch_use_threads,
      batch_stock_selection_threads: form.batch_threads,
    },
  }
  try {
    await run.start(payload)
    message.info('回测已启动，后台执行中，可随时中止。')
  } catch (err) {
    message.error(extractError(err))
  }
}

async function handleStop() {
  try {
    await run.stop()
    message.info('已请求中止，将在当前交易日结束后停止。')
  } catch (err) {
    message.error(extractError(err))
  }
}
</script>

<template>
  <NSpace vertical :size="16">
    <NCard title="回测配置">
      <RunProgress style="margin-bottom: 16px" @stop="handleStop" />
      <NForm label-placement="top" :disabled="loading || run.running">
        <NGrid :cols="'1 s:2 m:3'" responsive="screen" :x-gap="16" :y-gap="4">
          <NGi>
            <NFormItem label="策略模块">
              <NSelect v-model:value="form.strategy_module" :options="moduleOptions" filterable />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="策略类">
              <NSelect v-model:value="form.strategy_class" :options="classOptions" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="回测时间区间">
              <NDatePicker
                v-model:formatted-value="form.dateRange"
                type="daterange"
                value-format="yyyyMMdd"
                clearable
                style="width: 100%"
              />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="初始资金">
              <NInputNumber v-model:value="form.initial_amount" :min="0" :step="10000" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="手续费率">
              <NInputNumber v-model:value="form.commission_rate" :min="0" :step="0.0001" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="最低佣金">
              <NInputNumber v-model:value="form.min_commission" :min="0" :step="1" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="印花税率">
              <NInputNumber v-model:value="form.tax_rate" :min="0" :step="0.0001" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="单股仓位方式">
              <NSelect
                v-model:value="form.limit_vol_type"
                :options="[
                  { label: '按总资产比例', value: 'ratio' },
                  { label: '按固定金额', value: 'amount' },
                ]"
              />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem v-if="form.limit_vol_type === 'ratio'" label="单股上限比例 (max_vol_rate)">
              <NInputNumber v-model:value="form.max_vol_rate" :min="0" :step="0.01" style="width: 100%" />
            </NFormItem>
            <NFormItem v-else label="单股上限金额 (max_vol_amount)">
              <NInputNumber v-model:value="form.max_vol_amount" :min="0" :step="10000" style="width: 100%" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="多线程选股">
              <NSpace align="center">
                <NSwitch v-model:value="form.batch_use_threads" />
                <NText depth="3" style="font-size: 12px">关闭为单线程（便于调试）</NText>
              </NSpace>
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem label="选股线程数 (0=自动)">
              <NInputNumber
                v-model:value="form.batch_threads"
                :min="0"
                :step="1"
                :disabled="!form.batch_use_threads"
                style="width: 100%"
              />
            </NFormItem>
          </NGi>
        </NGrid>
        <NSpace>
          <NButton type="primary" :disabled="run.running" :loading="run.running" @click="handleRun">
            开始回测
          </NButton>
          <NButton v-if="run.running" type="error" ghost @click="handleStop">中止回测</NButton>
        </NSpace>
      </NForm>
    </NCard>

    <NCard title="历史回测">
      <HistoryTable />
    </NCard>
  </NSpace>
</template>
