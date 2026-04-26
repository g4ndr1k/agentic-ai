<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useFinanceStore } from '../stores/finance.js'
import { useOfflineSync } from '../composables/useOfflineSync.js'

const store = useFinanceStore()
const route = useRoute()
const { isOnline } = useOfflineSync(() => store.loadHealth({ forceFresh: true }))
const pageTitle = computed(() => route.meta?.title || 'Personal Wealth Management')

const txnCount = computed(() => {
  const n = store.health?.transaction_count ?? 0
  return n.toLocaleString('en-US')
})
</script>

<template>
  <header class="top-bar">
    <div class="title-block">
      <span class="title-eyebrow">Personal Wealth Management</span>
      <span class="title">{{ pageTitle }}</span>
    </div>
    <div class="sync-info">
      <!-- Privacy toggle — line-style SVG icon -->
      <button
        class="hide-toggle"
        :title="store.hideNumbers ? 'Show amounts' : 'Hide amounts'"
        @click="store.setHideNumbers(!store.hideNumbers)"
      >
        <svg v-if="store.hideNumbers" class="privacy-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 10s3.5-6 8-6 8 6 8 6-3.5 6-8 6-8-6-8-6z"/>
          <circle cx="10" cy="10" r="2.5"/>
          <line x1="3" y1="3" x2="17" y2="17"/>
        </svg>
        <svg v-else class="privacy-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 10s3.5-6 8-6 8 6 8 6-3.5 6-8 6-8-6-8-6z"/>
          <circle cx="10" cy="10" r="2.5"/>
        </svg>
      </button>

      <!-- LED status dot -->
      <span class="status-led" :class="{ ok: store.health?.status === 'ok' && isOnline }"></span>

      <!-- Transaction count -->
      <span v-if="store.health" class="txn-label">
        {{ txnCount }}&thinsp;<span class="txn-unit">TXNS</span>
        <span v-if="store.isReadOnly" class="ro-badge" title="Read-only · NAS replica">RO</span>
      </span>
      <span v-else class="txn-label connecting">connecting…</span>
    </div>
  </header>
</template>

<style scoped>
.hide-toggle {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0 2px;
  opacity: 0.75;
  line-height: 1;
  display: flex;
  align-items: center;
  color: inherit;
}
.hide-toggle:hover { opacity: 1; }

.privacy-icon {
  width: 18px;
  height: 18px;
  display: block;
}

/* Glowing LED indicator */
.status-led {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(255,255,255,0.25);
  flex-shrink: 0;
  box-shadow: none;
  transition: background 0.3s, box-shadow 0.3s;
}
.status-led.ok {
  background: #4ade80;
  box-shadow: 0 0 0 2px rgba(74,222,128,0.20), 0 0 6px rgba(74,222,128,0.60);
}

/* Transaction label */
.txn-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: rgba(255,255,255,0.85);
  display: flex;
  align-items: baseline;
  gap: 1px;
}
.txn-unit {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.10em;
  color: rgba(255,255,255,0.55);
}
.connecting {
  font-size: 10px;
  color: rgba(255,255,255,0.45);
  letter-spacing: 0.04em;
}
.ro-badge {
  font-size: 8px;
  font-weight: 800;
  letter-spacing: 0.08em;
  color: var(--warning);
  background: rgba(251,191,36,0.15);
  border: 1px solid rgba(251,191,36,0.30);
  border-radius: 4px;
  padding: 1px 4px;
  margin-left: 4px;
  vertical-align: 1px;
}
</style>
