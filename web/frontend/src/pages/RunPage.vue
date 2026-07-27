<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NCard, NSpin, NAlert, NText } from 'naive-ui'
import { getStrategies, getConfig } from '@/api/backtests'
import { extractError } from '@/api/client'
import type { AppConfig, StrategyInfo } from '@/types/backtest'

// P0 阶段：仅验证前后端联通（加载策略与配置）。完整表单在 P2 实现。
const loading = ref(true)
const errorMsg = ref('')
const strategies = ref<StrategyInfo[]>([])
const config = ref<AppConfig | null>(null)

onMounted(async () => {
  try {
    const [s, c] = await Promise.all([getStrategies(), getConfig()])
    strategies.value = s
    config.value = c
  } catch (err) {
    errorMsg.value = extractError(err)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <NSpin :show="loading">
    <NCard title="回测（脚手架验证）">
      <NAlert v-if="errorMsg" type="error" :title="'加载失败'">{{ errorMsg }}</NAlert>
      <template v-else>
        <NText depth="3">已连通后端 API。完整配置表单将在后续阶段实现。</NText>
        <p style="margin-top: 12px">
          <strong>可用策略：</strong>{{ strategies.map((s) => s.module).join('、') || '（无）' }}
        </p>
        <p v-if="config">
          <strong>当前策略：</strong>{{ config.strategy.strategy_module }}.{{ config.strategy.strategy_class }}
        </p>
        <p v-if="config">
          <strong>回测区间：</strong>{{ config.backtest.backtest_start_time }} ~ {{ config.backtest.backtest_end_time }}
        </p>
      </template>
    </NCard>
  </NSpin>
</template>
