<script setup lang="ts">
import { ref } from 'vue'
import { NModal, NCard, NCode, NSpin, NAlert } from 'naive-ui'
import { getCode } from '@/api/backtests'
import { extractError } from '@/api/client'

const show = ref(false)
const loading = ref(false)
const errorMsg = ref('')
const title = ref('')
const code = ref('')

async function open(runId: string, label: string) {
  show.value = true
  loading.value = true
  errorMsg.value = ''
  title.value = `策略代码 · ${label}`
  code.value = ''
  try {
    const data = await getCode(runId)
    code.value = data.code
    title.value = `策略代码 · ${label}（${data.file_name}）`
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
    <NCard :title="title" style="width: 900px; max-width: 92vw" closable @close="show = false">
      <NSpin :show="loading">
        <NAlert v-if="errorMsg" type="error" title="加载策略代码失败">{{ errorMsg }}</NAlert>
        <div v-else style="max-height: 70vh; overflow: auto">
          <NCode :code="code" language="python" show-line-numbers />
        </div>
      </NSpin>
    </NCard>
  </NModal>
</template>
