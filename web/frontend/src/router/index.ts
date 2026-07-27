import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

// 路由 → 6 大功能区。ResultPage/ComparePage/MarketBrowserPage 在后续阶段填充。
const routes: RouteRecordRaw[] = [
  { path: '/', name: 'dashboard', component: () => import('@/pages/DashboardPage.vue'), meta: { title: '总览' } },
  { path: '/run', name: 'run', component: () => import('@/pages/RunPage.vue'), meta: { title: '回测' } },
  { path: '/runs/:id', name: 'result', component: () => import('@/pages/ResultPage.vue'), meta: { title: '回测结果' } },
  { path: '/compare', name: 'compare', component: () => import('@/pages/ComparePage.vue'), meta: { title: '策略对比' } },
  { path: '/market', name: 'market', component: () => import('@/pages/MarketBrowserPage.vue'), meta: { title: '行情浏览' } },
]

const router = createRouter({
  history: createWebHistory('/'),
  routes,
})

export default router
