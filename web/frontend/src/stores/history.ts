import { defineStore } from 'pinia'
import { listBacktests, deleteBacktest } from '@/api/backtests'
import type { RunRecord } from '@/types/backtest'

// 历史回测记录缓存。
export const useHistoryStore = defineStore('history', {
  state: () => ({
    runs: [] as RunRecord[],
    loading: false,
  }),
  getters: {
    // 按 id 倒序（最新在前）。
    sorted: (state): RunRecord[] => state.runs.slice().reverse(),
  },
  actions: {
    async load() {
      this.loading = true
      try {
        this.runs = await listBacktests()
      } finally {
        this.loading = false
      }
    },
    async remove(runId: string) {
      await deleteBacktest(runId)
      this.runs = this.runs.filter((r) => r.id !== runId)
    },
    find(runId: string): RunRecord | undefined {
      return this.runs.find((r) => r.id === runId)
    },
  },
})
