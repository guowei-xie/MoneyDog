<script setup lang="ts">
import { ref } from 'vue'
import { NModal, NCard, NSpin, NAlert, NEmpty, NText } from 'naive-ui'
import KLineChart from './charts/KLineChart.vue'
import { getKline } from '@/api/backtests'
import { extractError } from '@/api/client'
import type { KLineData } from '@/types/backtest'

const show = ref(false)
const loading = ref(false)
const errorMsg = ref('')
const title = ref('')
const data = ref<KLineData | null>(null)

async function open(runId: string, code: string) {
  show.value = true
  loading.value = true
  errorMsg.value = ''
  data.value = null
  title.value = `K 线 · ${code}`
  try {
    data.value = await getKline(runId, code)
  } catch (err) {
    errorMsg.value = extractError(err)
  } finally {
    loading.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <NModal v-model:show="show">
    <NCard :title="title" style="width: 1100px; max-width: 94vw" closable @close="show = false">
      <NSpin :show="loading">
        <NAlert v-if="errorMsg" type="error" title="加载 K 线失败">{{ errorMsg }}</NAlert>
        <template v-else-if="data">
          <NEmpty v-if="data.bars.length === 0" description="该区间无行情数据" />
          <template v-else>
            <NText depth="3" style="font-size: 12px">
              红涨绿跌 · 买卖点标记（B 买入 / S 卖出）· 共 {{ data.markers.length }} 个成交点
            </NText>
            <KLineChart :bars="data.bars" :markers="data.markers" height="480px" />
          </template>
        </template>
      </NSpin>
    </NCard>
  </NModal>
</template>
