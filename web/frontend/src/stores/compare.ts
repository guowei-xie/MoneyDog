import { defineStore } from 'pinia'
import { getCurve, getBacktest } from '@/api/backtests'
import type { CurveSeries, RunRecord } from '@/types/backtest'

export interface CompareEntry {
  id: string
  record: RunRecord
  curve: CurveSeries
}

// 策略对比：按选中的 run_id 集合拉取各自曲线与记录，供叠加与指标对照。
export const useCompareStore = defineStore('compare', {
  state: () => ({
    entries: [] as CompareEntry[],
    loading: false,
  }),
  actions: {
    async load(ids: string[]) {
      this.loading = true
      try {
        const results = await Promise.all(
          ids.map(async (id) => {
            const [record, curve] = await Promise.all([getBacktest(id), getCurve(id)])
            return { id, record, curve } as CompareEntry
          }),
        )
        // 保持与传入 ids 一致的顺序
        this.entries = ids
          .map((id) => results.find((r) => r.id === id))
          .filter((e): e is CompareEntry => !!e)
      } finally {
        this.loading = false
      }
    },
    clear() {
      this.entries = []
    },
  },
})
