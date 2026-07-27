<script setup lang="ts">
import { computed } from 'vue'
import { NProgress, NButton, NSpace, NText, NTag } from 'naive-ui'
import { useRunStore } from '@/stores/run'

const run = useRunStore()

const stageLabel = computed(() => (run.stage === 'selection' ? '选股' : run.stage === 'backtest' ? '回测' : ''))
const progressText = computed(() => {
  if (!run.running) return ''
  if (!run.total) return `${stageLabel.value}准备中…`
  return `${stageLabel.value}进度：${run.current}/${run.total} 日`
})

const emit = defineEmits<{ (e: 'stop'): void }>()
</script>

<template>
  <div v-if="run.running" class="run-progress">
    <NSpace align="center" justify="space-between" style="margin-bottom: 8px">
      <NSpace align="center" :size="8">
        <NTag type="success" size="small" round>运行中</NTag>
        <NText depth="2">{{ run.strategyLabel }}</NText>
        <NText depth="3" v-if="run.period">· {{ run.period }}</NText>
      </NSpace>
      <NButton size="small" type="error" ghost @click="emit('stop')">中止回测</NButton>
    </NSpace>
    <NProgress
      type="line"
      :percentage="Math.round(run.percent * 10) / 10"
      :indicator-placement="'inside'"
      :status="'success'"
      processing
    />
    <NText depth="3" style="font-size: 12px">{{ progressText }}</NText>
  </div>
</template>

<style scoped>
.run-progress {
  padding: 12px 16px;
  border: 1px solid var(--n-border-color, #333);
  border-radius: 8px;
}
</style>
