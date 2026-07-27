import { defineStore } from 'pinia'
import { getStatus, runBacktest, stopBacktest } from '@/api/backtests'
import { formatPeriod, formatStrategyLabel } from '@/utils/format'
import type { RunBacktestRequest, RunStatus } from '@/types/backtest'

const POLL_INTERVAL_MS = 1000

// 回测运行状态机：负责启动/中止、进度轮询与刷新后的运行态恢复。
export const useRunStore = defineStore('run', {
  state: () => ({
    running: false,
    runId: null as string | null,
    stage: 'idle',
    percent: 0,
    current: 0,
    total: 0,
    strategyLabel: null as string | null,
    startedAt: null as string | null,
    period: null as string | null,
    lastFinishedRunId: null as string | null,
    lastStatus: null as string | null,
    _timer: null as number | null,
    _initialized: false,
  }),
  actions: {
    applyStatus(s: RunStatus) {
      const wasRunning = this.running
      this.running = s.running
      this.runId = s.run_id
      this.stage = s.stage
      this.percent = s.percent
      this.current = s.current
      this.total = s.total
      this.strategyLabel = s.strategy_label ?? this.strategyLabel
      this.startedAt = s.started_at ?? this.startedAt
      this.period = s.backtest_period ?? this.period
      this.lastFinishedRunId = s.last_finished_run_id ?? this.lastFinishedRunId
      this.lastStatus = s.last_status ?? this.lastStatus
      // 运行中 -> 结束的跳变：停止轮询（页面通过 watch(running) 感知结束并跳转结果页）
      if (wasRunning && !s.running) this.stopPolling()
    },
    async refresh() {
      const s = await getStatus()
      this.applyStatus(s)
    },
    startPolling() {
      if (this._timer !== null) return
      this._timer = window.setInterval(() => {
        this.refresh().catch(() => {
          /* 轮询失败静默重试，避免刷屏 */
        })
      }, POLL_INTERVAL_MS)
    },
    stopPolling() {
      if (this._timer !== null) {
        window.clearInterval(this._timer)
        this._timer = null
      }
    },
    // 应用挂载时调用一次：拉取当前状态，运行中则恢复轮询。
    async init() {
      if (this._initialized) return
      this._initialized = true
      try {
        await this.refresh()
        if (this.running) this.startPolling()
      } catch {
        /* 后端不可用时忽略，交由具体页面报错 */
      }
    },
    async start(payload: RunBacktestRequest) {
      const resp = await runBacktest(payload)
      this.running = true
      this.runId = resp.run_id
      this.stage = 'selection'
      this.percent = 0
      this.current = 0
      this.total = 0
      this.strategyLabel = formatStrategyLabel(payload.strategy)
      this.period = formatPeriod(payload.backtest)
      this.startPolling()
      return resp.run_id
    },
    async stop() {
      await stopBacktest()
    },
  },
})
