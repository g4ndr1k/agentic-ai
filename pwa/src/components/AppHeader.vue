<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useFinanceStore } from '../stores/finance.js'
import { useLayout } from '../composables/useLayout.js'

const store = useFinanceStore()
const route = useRoute()
const pageTitle = computed(() => route.meta?.title || 'Personal Finance')
const { layoutMode, toggleDesktopMode } = useLayout()
const layoutButtonLabel = computed(() => layoutMode.value === 'desktop' ? 'Auto Layout' : 'Desktop View')
</script>

<template>
  <header class="top-bar">
    <div class="title-block">
      <span class="title-eyebrow">Personal Finance</span>
      <span class="title">{{ pageTitle }}</span>
    </div>
    <div class="sync-info">
      <span class="status-dot" :class="{ ok: store.health?.status === 'ok' }"></span>
      <span v-if="store.health">
        {{ store.health.transaction_count }} txn
        <template v-if="store.reviewCount > 0"> · {{ store.reviewCount }} pending</template>
      </span>
      <span v-else>connecting…</span>
    </div>
    <button class="layout-toggle-btn" @click="toggleDesktopMode">
      {{ layoutButtonLabel }}
    </button>
  </header>
</template>

<style scoped>
.layout-toggle-btn {
  border: 1px solid rgba(255,255,255,0.14);
  background: rgba(255,255,255,0.08);
  color: #fff;
  border-radius: 999px;
  padding: 7px 11px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
  cursor: pointer;
}

.layout-toggle-btn:active {
  background: rgba(255,255,255,0.14);
}

@media (max-width: 430px) {
  .layout-toggle-btn {
    padding: 6px 9px;
    font-size: 10px;
  }
}
</style>
