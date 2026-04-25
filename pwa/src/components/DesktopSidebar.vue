<script setup>
import { computed } from 'vue'
import { useFinanceStore } from '../stores/finance.js'
import { useLayout } from '../composables/useLayout.js'
import { NAV_SVGS, EYE_SVG } from '../utils/icons.js'

const store = useFinanceStore()
const { setLayoutMode } = useLayout()

const txnCount = computed(() => {
  const n = store.health?.transaction_count ?? null
  return n !== null ? n.toLocaleString('en-US') : '—'
})
</script>

<template>
  <nav class="desktop-sidebar">
    <div class="desktop-sidebar__brand">
      <div class="desktop-sidebar__title">Personal Finance</div>
      <div class="desktop-sidebar__subtitle">Wealth Dashboard</div>
    </div>

    <div class="desktop-sidebar__nav">
      <RouterLink to="/" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.Dashboard"></span>
        <span>Dashboard</span>
      </RouterLink>
      <RouterLink to="/flows" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.Flows"></span>
        <span>Flows</span>
      </RouterLink>
      <RouterLink to="/wealth" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.Wealth"></span>
        <span>Wealth</span>
      </RouterLink>
      <RouterLink to="/holdings" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.Assets"></span>
        <span>Assets</span>
      </RouterLink>
      <RouterLink to="/transactions" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.Transactions"></span>
        <span>Transactions</span>
      </RouterLink>
      <RouterLink to="/goal" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.Goal"></span>
        <span>Goal</span>
      </RouterLink>
      <RouterLink to="/review" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.Review"></span>
        <span>Review</span>
        <span v-if="store.reviewCount > 0" class="desktop-sidebar__badge">
          {{ store.reviewCount > 99 ? '99+' : store.reviewCount }}
        </span>
      </RouterLink>
      <RouterLink to="/foreign" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS['Foreign Spend']"></span>
        <span>Foreign Spend</span>
      </RouterLink>
      <RouterLink to="/adjustment" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.Adjustment"></span>
        <span>Adjustment</span>
      </RouterLink>
      <RouterLink to="/audit" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.Audit"></span>
        <span>Audit</span>
      </RouterLink>
      <RouterLink to="/coretax" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.CoreTax"></span>
        <span>CoreTax</span>
      </RouterLink>
      <RouterLink to="/settings" class="desktop-sidebar__link">
        <span class="sidebar-icon" v-html="NAV_SVGS.Settings"></span>
        <span>Settings</span>
      </RouterLink>
    </div>

    <div class="desktop-sidebar__footer">
      <div class="desktop-sidebar__status">
        <span class="status-dot" :class="{ ok: store.health?.status === 'ok' }"></span>
        <span class="txn-count">{{ txnCount }}&thinsp;<span class="txn-unit">TXNS</span></span>
        <span v-if="store.isReadOnly" class="ro-indicator" v-html="EYE_SVG" title="Read-only · NAS replica"></span>
      </div>
      <button class="desktop-sidebar__mode-btn" @click="setLayoutMode('auto')">
        Auto Layout
      </button>
    </div>
  </nav>
</template>

<style scoped>
.sidebar-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--primary-deep);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0.75;
  transition: opacity 0.15s;
}
.sidebar-icon :deep(svg) { width: 16px; height: 16px; }

.desktop-sidebar__link:hover .sidebar-icon,
.desktop-sidebar__link.router-link-active .sidebar-icon {
  opacity: 1;
  color: var(--primary);
}

.desktop-sidebar__status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.txn-count {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255,255,255,0.7);
  display: flex;
  align-items: baseline;
  gap: 1px;
}
.txn-unit {
  font-size: 8px;
  font-weight: 800;
  letter-spacing: 0.10em;
  color: rgba(255,255,255,0.4);
}

.desktop-sidebar__mode-btn {
  margin-top: 10px;
  width: 100%;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.08);
  color: #fff;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}
.desktop-sidebar__mode-btn:hover { background: rgba(255,255,255,0.12); }

.ro-indicator {
  width: 14px;
  height: 14px;
  color: var(--warning);
  display: inline-flex;
  align-items: center;
  opacity: 0.7;
}
.ro-indicator :deep(svg) { width: 14px; height: 14px; }
</style>
