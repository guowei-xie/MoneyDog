<script setup lang="ts">
import { computed, h } from 'vue'
import { RouterView, RouterLink, useRoute } from 'vue-router'
import {
  NConfigProvider,
  NGlobalStyle,
  NMessageProvider,
  NDialogProvider,
  NLayout,
  NLayoutSider,
  NLayoutHeader,
  NLayoutContent,
  NMenu,
  darkTheme,
  type MenuOption,
} from 'naive-ui'

const route = useRoute()

// 左侧导航：对应 6 大功能区（回测结果为动态路由，不单列菜单项）。
const menuOptions: MenuOption[] = [
  { label: () => h(RouterLink, { to: '/' }, { default: () => '总览' }), key: 'dashboard' },
  { label: () => h(RouterLink, { to: '/run' }, { default: () => '回测' }), key: 'run' },
  { label: () => h(RouterLink, { to: '/compare' }, { default: () => '策略对比' }), key: 'compare' },
  { label: () => h(RouterLink, { to: '/market' }, { default: () => '行情浏览' }), key: 'market' },
]

// 结果页(/runs/:id)高亮回归到“回测”一栏。
const activeKey = computed(() => {
  const name = route.name
  if (name === 'result') return 'run'
  return (name as string) ?? 'dashboard'
})

const themeOverrides = {
  common: {
    primaryColor: '#22c55e',
    primaryColorHover: '#4ade80',
    primaryColorPressed: '#16a34a',
  },
}
</script>

<template>
  <NConfigProvider :theme="darkTheme" :theme-overrides="themeOverrides">
    <NGlobalStyle />
    <NMessageProvider>
      <NDialogProvider>
        <NLayout style="height: 100vh">
          <NLayoutHeader bordered class="app-header">
            <div class="logo">
              <span class="logo-badge">M</span>
              <div>
                <div class="logo-title">MoneyDog 量化交易平台</div>
                <div class="logo-sub">本地 DuckDB · 策略回测 · 账户分析</div>
              </div>
            </div>
          </NLayoutHeader>
          <NLayout has-sider style="height: calc(100vh - 60px)">
            <NLayoutSider bordered :width="180" :native-scrollbar="false">
              <NMenu :options="menuOptions" :value="activeKey" />
            </NLayoutSider>
            <NLayoutContent :native-scrollbar="false" content-style="padding: 20px;">
              <RouterView />
            </NLayoutContent>
          </NLayout>
        </NLayout>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped>
.app-header {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 20px;
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: #22c55e;
  color: #06110a;
  font-weight: 700;
}
.logo-title {
  font-size: 16px;
  font-weight: 600;
}
.logo-sub {
  font-size: 12px;
  opacity: 0.6;
}
</style>
