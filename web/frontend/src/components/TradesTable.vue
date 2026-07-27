<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { NDataTable, NInput, NSpace, NSwitch, NText, NTag, type DataTableColumns } from 'naive-ui'
import { formatMoney, formatPct } from '@/utils/format'
import type { Trade } from '@/types/backtest'

const props = defineProps<{ trades: Trade[] }>()
const emit = defineEmits<{ (e: 'drill', code: string): void }>()

const keyword = ref('')
const onlyClosed = ref(false)

const filtered = computed(() =>
  props.trades.filter((t) => {
    if (onlyClosed.value && !t.closed) return false
    if (keyword.value && !t.code.toLowerCase().includes(keyword.value.toLowerCase())) return false
    return true
  }),
)

function pctCell(v: number | null) {
  if (v === null || v === undefined) return h(NText, { depth: 3 }, () => '-')
  const color = v > 0 ? '#22c55e' : v < 0 ? '#ef4444' : undefined
  return h('span', { style: { color } }, formatPct(v))
}

const numSorter = (key: keyof Trade) => (a: Trade, b: Trade) =>
  ((a[key] as number) ?? -Infinity) - ((b[key] as number) ?? -Infinity)

const columns: DataTableColumns<Trade> = [
  {
    title: '股票',
    key: 'code',
    fixed: 'left',
    width: 110,
    render: (t) =>
      h('a', { style: { color: '#38bdf8', cursor: 'pointer' }, onClick: () => emit('drill', t.code) }, t.code),
  },
  { title: '建仓时间', key: 'open_time', render: (t) => t.open_time ?? '-' },
  { title: '建仓价', key: 'open_price', align: 'right', render: (t) => formatMoney(t.open_price) },
  { title: '清仓时间', key: 'close_time', render: (t) => t.close_time ?? '-' },
  { title: '清仓价', key: 'close_price', align: 'right', render: (t) => formatMoney(t.close_price) },
  {
    title: '净涨跌幅',
    key: 'net_pct',
    align: 'right',
    sorter: numSorter('net_pct'),
    render: (t) => pctCell(t.net_pct),
  },
  {
    title: '毛涨跌幅',
    key: 'gross_pct',
    align: 'right',
    sorter: numSorter('gross_pct'),
    render: (t) => pctCell(t.gross_pct),
  },
  {
    title: '持仓天数',
    key: 'hold_days',
    align: 'right',
    sorter: numSorter('hold_days'),
    render: (t) => t.hold_days ?? '-',
  },
  { title: '总成本', key: 'cost', align: 'right', sorter: numSorter('cost'), render: (t) => formatMoney(t.cost, 0) },
  {
    title: '状态',
    key: 'closed',
    render: (t) =>
      h(NTag, { size: 'small', type: t.closed ? 'default' : 'warning', round: true }, () =>
        t.closed ? '已平仓' : '持仓中',
      ),
  },
]
</script>

<template>
  <div>
    <NSpace align="center" style="margin-bottom: 12px">
      <NInput v-model:value="keyword" placeholder="搜索股票代码" clearable style="width: 200px" />
      <NSpace align="center" :size="6">
        <NSwitch v-model:value="onlyClosed" />
        <NText depth="3" style="font-size: 12px">只看已平仓</NText>
      </NSpace>
      <NText depth="3" style="font-size: 12px">共 {{ filtered.length }} 笔</NText>
    </NSpace>
    <NDataTable
      :columns="columns"
      :data="filtered"
      :pagination="{ pageSize: 15 }"
      :scroll-x="1000"
      size="small"
    />
  </div>
</template>
