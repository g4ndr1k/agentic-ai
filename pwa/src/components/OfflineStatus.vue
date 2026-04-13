<script setup>
import { useOfflineSync } from '../composables/useOfflineSync.js'
import { useFinanceStore } from '../stores/finance.js'

const store = useFinanceStore()
const { isOnline } = useOfflineSync(() => store.bootstrap())
</script>

<template>
  <Transition name="offline-slide">
    <div v-if="!isOnline" class="offline-banner" role="alert" aria-live="assertive">
      <span class="offline-icon">⚡</span>
      <span>You're offline — showing last available data</span>
    </div>
  </Transition>
</template>

<style scoped>
.offline-banner {
  position: fixed;
  top: env(safe-area-inset-top, 0);
  left: 0;
  right: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #f59e0b;
  color: #1c1917;
  font-size: 14px;
  font-weight: 600;
  text-align: center;
  justify-content: center;
}

.offline-icon { font-size: 16px; }

.offline-slide-enter-active,
.offline-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.offline-slide-enter-from,
.offline-slide-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}
</style>
