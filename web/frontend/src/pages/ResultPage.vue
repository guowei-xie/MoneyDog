<script setup lang="ts">
import { useRoute } from 'vue-router'
import { NCard, NText } from 'naive-ui'

const route = useRoute()
</script>

<template>
  <NCard :title="`回测结果 · ${route.params.id}`">
    <NText depth="3">结果详情（指标 / 曲线 / 交易表）将在 P2–P5 阶段实现。</NText>
  </NCard>
</template>
