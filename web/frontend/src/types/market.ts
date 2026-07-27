export interface StockInfo {
  code: string
}

export interface IndexInfo {
  code: string
  name: string
}

export interface Coverage {
  start: string | null
  end: string | null
  count: number
}

export interface CoverageInfo {
  daily: Coverage
  minute: Coverage | null
}
