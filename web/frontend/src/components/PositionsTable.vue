<script setup lang="ts">
import { NDataTable, type DataTableColumns } from 'naive-ui'
import { formatMoney } from '@/utils/format'
import { numSorter } from '@/utils/table'
import type { PositionRow } from '@/types/backtest'

defineProps<{ positions: PositionRow[] }>()

const columns: DataTableColumns<PositionRow> = [
  { title: '交易日', key: 'trade_date', fixed: 'left', width: 120, sorter: (a, b) => a.trade_date.localeCompare(b.trade_date) },
  { title: '持仓数', key: 'stock_count', align: 'right', sorter: numSorter<PositionRow>('stock_count') },
  { title: '总资产', key: 'total_assets', align: 'right', sorter: numSorter<PositionRow>('total_assets'), render: (r) => formatMoney(r.total_assets, 0) },
  { title: '持仓市值', key: 'stock_value', align: 'right', sorter: numSorter<PositionRow>('stock_value'), render: (r) => formatMoney(r.stock_value, 0) },
  { title: '持仓成本', key: 'stock_cost', align: 'right', sorter: numSorter<PositionRow>('stock_cost'), render: (r) => formatMoney(r.stock_cost, 0) },
  { title: '可用资金', key: 'available_amount', align: 'right', sorter: numSorter<PositionRow>('available_amount'), render: (r) => formatMoney(r.available_amount, 0) },
]
</script>

<template>
  <NDataTable
    :columns="columns"
    :data="positions"
    :pagination="{ pageSize: 15 }"
    :scroll-x="720"
    size="small"
  />
</template>
