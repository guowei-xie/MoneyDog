import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端构建与开发服务器配置。
// - base '/'：与 FastAPI 同源托管；
// - dev proxy：把 /api 代理到后端 uvicorn(:8000)，使 axios baseURL '/api' 在开发/生产一致；
// - build.outDir 'dist'：产物由 web/server.py 托管。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
