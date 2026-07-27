import axios, { type AxiosError } from 'axios'

// 统一 axios 实例：baseURL '/api'，在开发（Vite 代理）与生产（同源）下均生效。
const client = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

// 从后端错误响应中提取可读信息（FastAPI 通常返回 {detail: string}）。
export function extractError(err: unknown): string {
  const axiosErr = err as AxiosError<{ detail?: string }>
  if (axiosErr?.response) {
    const detail = axiosErr.response.data?.detail
    if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail)
    return `HTTP ${axiosErr.response.status}`
  }
  if (axiosErr?.message) return axiosErr.message
  return String(err)
}

export default client
