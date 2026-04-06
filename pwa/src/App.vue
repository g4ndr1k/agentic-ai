<template>
  <div class="app">
    <!-- Top bar -->
    <header class="top-bar">
      <div class="title-block">
        <span class="title-eyebrow">Personal Finance</span>
        <span class="title">Wealth</span>
      </div>
      <div class="sync-info">
        <span class="status-dot" :class="{ ok: store.health?.status === 'ok' }"></span>
        <span v-if="store.health">
          {{ store.health.transaction_count }} txn
          <template v-if="store.reviewCount > 0"> · {{ store.reviewCount }} pending</template>
        </span>
        <span v-else>connecting…</span>
      </div>
    </header>

    <!-- Page content -->
    <main class="content">
      <RouterView />
    </main>

    <!-- Bottom navigation -->
    <nav class="bottom-nav">
      <RouterLink to="/" class="nav-item">
        <span class="nav-icon">📊</span>
        <span class="nav-label">Flows</span>
      </RouterLink>
      <RouterLink to="/wealth" class="nav-item">
        <span class="nav-icon">💰</span>
        <span class="nav-label">Wealth</span>
      </RouterLink>
      <RouterLink to="/holdings" class="nav-item">
        <span class="nav-icon">🗂️</span>
        <span class="nav-label">Assets</span>
      </RouterLink>
      <RouterLink to="/transactions" class="nav-item">
        <span class="nav-icon">🧾</span>
        <span class="nav-label">Txns</span>
      </RouterLink>
      <RouterLink to="/review" class="nav-item">
        <span class="nav-icon">🔎</span>
        <span class="nav-label">Review</span>
        <span v-if="store.reviewCount > 0" class="nav-badge">
          {{ store.reviewCount > 99 ? '99+' : store.reviewCount }}
        </span>
      </RouterLink>
      <RouterLink to="/settings" class="nav-item">
        <span class="nav-icon">⚙︎</span>
        <span class="nav-label">More</span>
      </RouterLink>
    </nav>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useFinanceStore } from './stores/finance.js'

const store = useFinanceStore()
onMounted(() => store.bootstrap())
</script>
