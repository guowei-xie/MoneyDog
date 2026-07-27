<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { echarts, type EChartsOption } from '@/utils/echarts'

// 通用 ECharts 挂载组件：负责 init/setOption/resize/dispose 生命周期，
// 使用方仅需传入 option。暗色主题、随容器自适应。
const props = withDefaults(defineProps<{ option: EChartsOption; height?: string }>(), {
  height: '360px',
})

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

function render() {
  if (chart) chart.setOption(props.option, true)
}

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value, 'dark')
  render()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(el.value)
})

// option 由各图表以 computed 传入，每次变化都是新对象引用，浅层 watch 即可触发，
// 避免 deep 递归遍历大数据数组的开销。
watch(() => props.option, render)

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" :style="{ width: '100%', height: props.height }" />
</template>
