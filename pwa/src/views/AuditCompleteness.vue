<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useFinanceStore } from '../stores/finance.js'
import { api } from '../api/client.js'

const store = useFinanceStore()
const loading = ref(false)
const error = ref('')
const data = ref(null)

const endMonth = computed(() => store.dashboardEndMonth)
const startMonth = computed(() => {
  // Always show 3 months ending at dashboardEndMonth
  const em = endMonth.value
  if (!em || em.length !== 7) return ''
  let y = parseInt(em.slice(0, 4))
  let m = parseInt(em.slice(5, 7)) - 2
  if (m <= 0) { m += 12; y -= 1 }
  return `${y}-${String(m).padStart(2, '0')}`
})

// Compute summary stats
const stats = computed(() => {
  if (!data.value) return { total: 0, ok: 0, missing: 0 }
  let total = 0, ok = 0, missing = 0
  for (const entity of data.value.entities) {
    for (const m of data.value.months) {
      total++
      if (entity.months[m]) ok++
      else missing++
    }
  }
  return { total, ok, missing }
})

// Determine if a cell is "missing" vs entity didn't exist at all in prior months
function cellStatus(entity, month, monthIdx) {
  const months = data.value.months
  const files = entity.months[month]
  if (files) return 'present'

  // Check if entity appeared in any earlier month
  const hasEarlier = months.slice(0, monthIdx).some(m => entity.months[m])
  // Check if entity appears in any later month
  const hasLater = months.slice(monthIdx + 1).some(m => entity.months[m])

  if (hasEarlier || hasLater) return 'missing'
  return 'new'  // entity doesn't exist in any month — not missing, just not started yet
}

async function load(forceFresh = true) {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.auditCompleteness(startMonth.value, endMonth.value, { forceFresh })
  } catch (e) {
    error.value = e.message || 'Failed to load audit data'
  } finally {
    loading.value = false
  }
}

watch([startMonth, endMonth], () => { load() })
onMounted(() => { load() })
</script>

<template>
  <div class="audit-view">
    <!-- Header -->
    <div class="audit-header">
      <div class="audit-title-row">
        <h1 class="audit-title">📋 Completeness Audit</h1>
        <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load(true)">
          {{ loading ? 'Loading…' : 'Refresh' }}
        </button>
      </div>
      <p class="audit-subtitle">
        PDF document coverage for the last 3 months.
        Missing statements from entities seen in other months are highlighted.
      </p>
    </div>

    <!-- Loading -->
    <div v-if="loading && !data" class="loading"><div class="spinner"></div> Loading audit…</div>

    <!-- Error -->
    <div v-else-if="error" class="alert alert-error">
      ❌ {{ error }}
      <button class="btn btn-sm btn-ghost" style="margin-left:auto" @click="load">Retry</button>
    </div>

    <!-- Empty -->
    <div v-else-if="data && data.entities.length === 0" class="card" style="margin-top:16px">
      <div class="empty-state" style="padding:32px 16px;text-align:center">
        <div style="font-size:40px;margin-bottom:12px">📂</div>
        <div style="font-weight:600;margin-bottom:6px">No PDF files found</div>
        <div class="e-sub">No recognized bank statement PDFs in pdf_inbox or pdf_unlocked.</div>
      </div>
    </div>

    <!-- Audit table -->
    <template v-else-if="data">
      <!-- Summary bar -->
      <div class="audit-summary">
        <span class="audit-badge audit-badge-ok">✅ {{ stats.ok }} found</span>
        <span v-if="stats.missing > 0" class="audit-badge audit-badge-missing">❌ {{ stats.missing }} missing</span>
        <span class="audit-badge audit-badge-total">{{ stats.total }} total</span>
      </div>

      <!-- Table -->
      <div class="audit-table-wrap">
        <table class="audit-table">
          <thead>
            <tr>
              <th class="audit-entity-col">Entity</th>
              <th v-for="(ml, i) in data.month_labels" :key="data.months[i]" class="audit-month-col">
                {{ ml }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entity in data.entities" :key="entity.key">
              <td class="audit-entity-col">
                <span class="audit-entity-label">{{ entity.label }}</span>
              </td>
              <td
                v-for="(month, mIdx) in data.months"
                :key="month"
                class="audit-cell"
                :class="'audit-cell--' + cellStatus(entity, month, mIdx)"
              >
                <template v-if="entity.months[month]">
                  <div class="audit-cell-present">
                    <span class="audit-check">✅</span>
                    <span class="audit-info">{{ entity.months[month].map(f => f.info).join(', ') }}</span>
                  </div>
                  <div class="audit-file-count">{{ entity.months[month].length }} file{{ entity.months[month].length > 1 ? 's' : '' }}</div>
                </template>
                <template v-else-if="cellStatus(entity, month, mIdx) === 'missing'">
                  <div class="audit-cell-missing">❌ Missing</div>
                </template>
                <template v-else>
                  <div class="audit-cell-na">—</div>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.audit-view {
  max-width: 100%;
}

.audit-header {
  padding: 0 16px 12px;
}

.audit-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.audit-title {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.03em;
  margin: 0;
}

.audit-subtitle {
  font-size: 12px;
  color: var(--text-muted);
  margin: 6px 0 0;
}

.audit-summary {
  display: flex;
  gap: 10px;
  padding: 8px 16px;
  flex-wrap: wrap;
}

.audit-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
}

.audit-badge-ok {
  background: var(--income-bg);
  color: #15803d;
}
.audit-badge-missing {
  background: var(--expense-bg);
  color: #991b1b;
}
.audit-badge-total {
  background: rgba(148, 163, 184, 0.12);
  color: var(--text-muted);
}

.audit-table-wrap {
  padding: 0 16px 24px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.audit-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
}

.audit-table thead th {
  position: sticky;
  top: 0;
  background: var(--bg);
  padding: 10px 12px;
  text-align: center;
  font-weight: 700;
  font-size: 12px;
  color: var(--text-muted);
  border-bottom: 2px solid var(--border);
  white-space: nowrap;
  z-index: 1;
}

.audit-entity-col {
  text-align: left;
  padding: 10px 12px;
  font-weight: 600;
  white-space: nowrap;
  border-bottom: 1px solid var(--border);
}

.audit-entity-label {
  font-size: 13px;
}

.audit-month-col {
  min-width: 120px;
}

.audit-cell {
  text-align: center;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}

.audit-cell--present {
  background: rgba(22, 163, 74, 0.04);
}

.audit-cell--missing {
  background: rgba(220, 38, 38, 0.06);
}

.audit-cell-present {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.audit-check {
  font-size: 14px;
}

.audit-info {
  font-size: 11px;
  font-weight: 700;
  color: var(--text);
}

.audit-file-count {
  font-size: 10px;
  color: var(--text-muted);
}

.audit-cell-missing {
  font-size: 12px;
  font-weight: 700;
  color: #dc2626;
}

.audit-cell-na {
  font-size: 12px;
  color: var(--border);
}

/* Desktop dark theme overrides */
:deep(.desktop-shell) .audit-title {
  color: var(--text);
}

:deep(.desktop-shell) .audit-subtitle {
  color: var(--text-muted);
}

:deep(.desktop-shell) .audit-table thead th {
  background: var(--card);
}

:deep(.desktop-shell) .audit-cell--present {
  background: rgba(22, 163, 74, 0.08);
}

:deep(.desktop-shell) .audit-cell--missing {
  background: rgba(220, 38, 38, 0.10);
}

:deep(.desktop-shell) .audit-entity-label {
  color: var(--text);
}

:deep(.desktop-shell) .audit-info {
  color: var(--text);
}

:deep(.desktop-shell) .audit-cell-missing {
  color: #f87171;
}

:deep(.desktop-shell) .audit-badge-ok {
  background: rgba(22, 163, 74, 0.15);
  color: #4ade80;
}

:deep(.desktop-shell) .audit-badge-missing {
  background: rgba(220, 38, 38, 0.15);
  color: #f87171;
}

:deep(.desktop-shell) .audit-badge-total {
  background: rgba(148, 163, 184, 0.10);
  color: var(--text-muted);
}
</style>
