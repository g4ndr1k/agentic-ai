<template>
  <div :class="['settings-page', { 'settings-page--desktop': isDesktop }]">
    <div v-if="!isDesktop" class="section-hd">
      <span class="settings-head-icon" v-html="NAV_SVGS.CoreTax"></span> CoreTax SPT
    </div>

    <nav v-if="isDesktop" class="settings-sub-nav">
      <div class="settings-sub-nav__title">CoreTax SPT</div>
      <button
        v-for="item in sections"
        :key="item.id"
        class="settings-sub-nav__item"
        :class="{ 'is-active': activeSection === item.id }"
        @click="setActiveSection(item.id)"
      >
        <span class="settings-sub-nav__icon" v-html="item.icon"></span>
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <div class="settings-content">
      <div v-if="isDesktop" class="section-hd">
        <span class="settings-head-icon" v-html="NAV_SVGS.CoreTax"></span> CoreTax SPT
      </div>

      <div :key="isDesktop ? activeSection : 'all'" class="settings-grid">
        <div class="setting-card" v-show="!isDesktop || activeSection === 'reporting-period'">
          <div class="setting-title"><span class="setting-title-icon" v-html="NAV_SVGS.Dashboard"></span> Reporting Period</div>
          <div class="setting-desc">
            Choose the reporting range for the financial statement modal. CoreTax snapshot follows the end month.
          </div>
          <div class="setting-row setting-row-range">
            <div class="range-field">
              <label class="range-label">Start Month</label>
              <select
                class="range-select"
                :value="store.reportingStartMonth"
                @change="store.setReportingRange($event.target.value, store.reportingEndMonth)"
              >
                <option
                  v-for="option in store.dashboardMonthOptions.filter(option => option.value <= store.reportingEndMonth)"
                  :key="`report-start-${option.value}`"
                  :value="option.value"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
            <div class="range-field">
              <label class="range-label">End Month</label>
              <select
                class="range-select"
                :value="store.reportingEndMonth"
                @change="store.setReportingRange(store.reportingStartMonth, $event.target.value)"
              >
                <option
                  v-for="option in store.dashboardMonthOptions.filter(option => option.value >= store.reportingStartMonth)"
                  :key="`report-end-${option.value}`"
                  :value="option.value"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
          </div>
          <div class="setting-desc" style="margin-top:10px">
            Active period: <strong>{{ store.reportingRangeLabel }}</strong>
          </div>
          <div class="setting-desc" style="margin-top:6px">
            Closing snapshot date: <strong>{{ snapshotDate }}</strong>
          </div>
        </div>

        <div class="setting-card" v-show="!isDesktop || activeSection === 'generate-fs'">
          <div class="setting-title"><span class="setting-title-icon" v-html="NAV_SVGS.Audit"></span> Generate Financial Statement</div>
          <div class="setting-desc">
            Opens the existing financial statement modal using the reporting period above.
          </div>
          <div class="setting-row" style="margin-top:12px">
            <button class="btn" @click="openStatement" :disabled="!store.reportingStartMonth || !store.reportingEndMonth">
              Generate Financial Statement
            </button>
          </div>
        </div>

        <div class="setting-card" v-show="!isDesktop || activeSection === 'template-picker'">
          <div class="setting-title"><span class="setting-title-icon" v-html="NAV_SVGS.CoreTax"></span> CoreTax SPT Template</div>
          <div class="setting-desc">
            Pick the annual XLSX template from <code>data/coretax/templates/</code>.
          </div>
          <div class="setting-row template-row">
            <select class="range-select" v-model="selectedTemplate" :disabled="templatesState.loading || !templates.length">
              <option value="">Select template…</option>
              <option v-for="template in templates" :key="template.name" :value="template.name">
                {{ template.name }}
              </option>
            </select>
            <button class="btn btn-ghost" @click="loadTemplates" :disabled="templatesState.loading">
              {{ templatesState.loading ? 'Refreshing…' : 'Refresh' }}
            </button>
          </div>
          <div v-if="templatesState.error" class="alert alert-error" style="margin-top:10px">
            {{ templatesState.error }}
          </div>
          <div v-else-if="!templatesState.loading && !templates.length" class="setting-desc" style="margin-top:10px">
            No templates found. Copy the yearly CoreTax workbook into <code>data/coretax/templates/</code>.
          </div>
          <div v-else-if="selectedTemplateMeta" class="setting-desc" style="margin-top:10px">
            Last modified {{ formatDateTime(selectedTemplateMeta.modified_at) }} · {{ formatBytes(selectedTemplateMeta.size_bytes) }}
          </div>
        </div>

        <div class="setting-card" v-show="!isDesktop || activeSection === 'generate-coretax'">
          <div class="setting-title"><span class="setting-title-icon" v-html="NAV_SVGS.CoreTax"></span> Generate CoreTax SPT</div>
          <div class="setting-desc">
            Preview first. Generation stays disabled until a dry run succeeds for the selected template and snapshot.
          </div>
          <div class="action-row">
            <button class="btn" @click="runPreview" :disabled="!canRun || previewState.loading">
              {{ previewState.loading ? 'Previewing…' : 'Preview (dry run)' }}
            </button>
            <button class="btn" @click="generateXlsx" :disabled="!canGenerate || generateState.loading">
              {{ generateState.loading ? 'Generating…' : 'Generate XLSX' }}
            </button>
            <button v-if="generateState.auditFilename" class="btn btn-ghost" @click="downloadAuditLog" :disabled="auditState.loading">
              {{ auditState.loading ? 'Downloading…' : 'Download audit log' }}
            </button>
          </div>
          <div v-if="previewState.error" class="alert alert-error" style="margin-top:10px">{{ previewState.error }}</div>
          <div v-if="generateState.error" class="alert alert-error" style="margin-top:10px">{{ generateState.error }}</div>
          <div v-if="generateState.success" class="alert alert-success" style="margin-top:10px">{{ generateState.success }}</div>

          <div v-if="previewResult" class="preview-summary">
            <div class="preview-summary__line ok">✔ {{ previewResult.filled_count }} rows filled</div>
            <details class="preview-summary__line warn" :open="previewResult.unmatched_count > 0">
              <summary>⚠ {{ previewResult.unmatched_count }} unmatched</summary>
              <ul>
                <li v-for="row in unmatchedRows" :key="`unmatched-${row.xlsx_row}`">
                  Row {{ row.xlsx_row }} — {{ row.raw_keterangan || '(blank)' }}
                  <span v-if="row.warnings?.length"> · {{ row.warnings.join('; ') }}</span>
                </li>
              </ul>
            </details>
            <details class="preview-summary__line warn" :open="previewResult.aggregated_count > 0">
              <summary>⚠ {{ previewResult.aggregated_count }} aggregated</summary>
              <ul>
                <li v-for="row in aggregatedRows" :key="`agg-${row.xlsx_row}`">
                  Row {{ row.xlsx_row }} — {{ row.warnings.join('; ') }}
                </li>
              </ul>
            </details>
            <details class="preview-summary__line warn" :open="previewResult.currency_warning_count > 0">
              <summary>⚠ {{ previewResult.currency_warning_count }} currency warnings</summary>
              <ul>
                <li v-for="row in currencyRows" :key="`fx-${row.xlsx_row}`">
                  Row {{ row.xlsx_row }} — {{ row.warnings.join('; ') }}
                </li>
              </ul>
            </details>
            <details class="preview-summary__line info" :open="previewResult.unused_pwm_rows?.length > 0">
              <summary>ⓘ {{ previewResult.unused_pwm_rows?.length || 0 }} unused PWM rows</summary>
              <ul>
                <li v-for="row in previewResult.unused_pwm_rows || []" :key="`${row.kind}-${row.id}`">
                  {{ row.kind }} — {{ row.institution }}<span v-if="row.account"> / {{ row.account }}</span> / {{ row.owner }}
                </li>
              </ul>
            </details>
          </div>
        </div>
      </div>

      <FinancialStatementModal
        :open="statementOpen"
        :start="store.reportingStartMonth"
        :end="store.reportingEndMonth"
        @close="statementOpen = false"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client.js'
import FinancialStatementModal from '../components/FinancialStatementModal.vue'
import { useLayout } from '../composables/useLayout.js'
import { useFinanceStore } from '../stores/finance.js'
import { NAV_SVGS } from '../utils/icons.js'

const store = useFinanceStore()
const { isDesktop } = useLayout()

const SECTION_KEY = 'coretax_active_section'
const sections = [
  { id: 'reporting-period', label: 'Reporting Period', icon: NAV_SVGS.Dashboard },
  { id: 'generate-fs', label: 'Generate FS', icon: NAV_SVGS.Audit },
  { id: 'template-picker', label: 'Template', icon: NAV_SVGS.CoreTax },
  { id: 'generate-coretax', label: 'Generate CoreTax', icon: NAV_SVGS.CoreTax },
]

function readStoredSection() {
  try { return localStorage.getItem(SECTION_KEY) || 'reporting-period' } catch { return 'reporting-period' }
}

const activeSection = ref(readStoredSection())
const statementOpen = ref(false)
const templates = ref([])
const selectedTemplate = ref('')
const previewState = ref({ loading: false, error: '', result: null })
const generateState = ref({ loading: false, error: '', success: '', auditFilename: '' })
const auditState = ref({ loading: false, error: '' })
const templatesState = ref({ loading: false, error: '' })

function setActiveSection(id) {
  activeSection.value = id
  try { localStorage.setItem(SECTION_KEY, id) } catch {}
}

function monthEndDate(monthKey) {
  if (!/^\d{4}-\d{2}$/.test(monthKey || '')) return ''
  const [year, month] = monthKey.split('-').map(Number)
  const lastDay = new Date(year, month, 0).getDate()
  return `${year}-${String(month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`
}

const snapshotDate = computed(() => monthEndDate(store.reportingEndMonth))
const selectedTemplateMeta = computed(() => templates.value.find(item => item.name === selectedTemplate.value) || null)
const previewResult = computed(() => previewState.value.result)
const unmatchedRows = computed(() => (previewResult.value?.rows || []).filter(row => row.status === 'unmatched'))
const aggregatedRows = computed(() => (previewResult.value?.rows || []).filter(row => row.status === 'aggregated'))
const currencyRows = computed(() => (previewResult.value?.rows || []).filter(row => row.status === 'currency_warning'))
const canRun = computed(() => Boolean(selectedTemplate.value && snapshotDate.value))
const canGenerate = computed(() => {
  if (!canRun.value || !previewResult.value) return false
  return previewResult.value.snapshot_date === snapshotDate.value && generateState.value.loading === false
})

function openStatement() {
  if (!store.reportingStartMonth || !store.reportingEndMonth) return
  statementOpen.value = true
}

async function loadTemplates() {
  templatesState.value = { loading: true, error: '' }
  try {
    const response = await api.coretaxTemplates({ forceFresh: true })
    templates.value = response.templates || []
    if (selectedTemplate.value && !templates.value.some(item => item.name === selectedTemplate.value)) {
      selectedTemplate.value = ''
    }
    templatesState.value = { loading: false, error: '' }
  } catch (error) {
    templatesState.value = { loading: false, error: error?.message || String(error) }
  }
}

async function runPreview() {
  if (!canRun.value) return
  previewState.value = { loading: true, error: '', result: null }
  generateState.value = { loading: false, error: '', success: '', auditFilename: '' }
  try {
    const result = await api.coretaxPreview({ template: selectedTemplate.value, snapshot_date: snapshotDate.value })
    previewState.value = { loading: false, error: '', result }
  } catch (error) {
    previewState.value = { loading: false, error: error?.message || String(error), result: null }
  }
}

async function generateXlsx() {
  if (!canGenerate.value) return
  generateState.value = { loading: true, error: '', success: '', auditFilename: '' }
  try {
    const response = await api.coretaxGenerate({ template: selectedTemplate.value, snapshot_date: snapshotDate.value })
    const blob = await response.blob()
    const disposition = response.headers.get('Content-Disposition') || ''
    const headerAudit = response.headers.get('X-Coretax-Audit-File') || ''
    const match = disposition.match(/filename="?([^";]+)"?/) || disposition.match(/filename\*=UTF-8''([^;]+)/)
    const filename = decodeURIComponent(match?.[1] || `CoreTax_${snapshotDate.value}.xlsx`)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
    generateState.value = {
      loading: false,
      error: '',
      success: `${filename} downloaded.`,
      auditFilename: headerAudit,
    }
  } catch (error) {
    generateState.value = { loading: false, error: error?.message || String(error), success: '', auditFilename: '' }
  }
}

async function downloadAuditLog() {
  if (!generateState.value.auditFilename) return
  auditState.value = { loading: true, error: '' }
  try {
    const payload = await api.coretaxAudit(generateState.value.auditFilename, { forceFresh: true })
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = generateState.value.auditFilename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
    auditState.value = { loading: false, error: '' }
  } catch (error) {
    auditState.value = { loading: false, error: error?.message || String(error) }
    generateState.value = { ...generateState.value, error: error?.message || String(error) }
  }
}

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDateTime(value) {
  if (!value) return '—'
  try { return new Date(value).toLocaleString() } catch { return value }
}

onMounted(loadTemplates)
</script>

<style scoped>
.settings-page {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}
.settings-page--desktop {
  grid-template-columns: 240px minmax(0, 1fr);
  align-items: start;
}
.settings-sub-nav {
  position: sticky;
  top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  background: rgba(14, 18, 24, 0.92);
}
.settings-sub-nav__title {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.55);
  margin-bottom: 4px;
}
.settings-sub-nav__item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.82);
  cursor: pointer;
  text-align: left;
}
.settings-sub-nav__item.is-active {
  border-color: rgba(108, 163, 255, 0.35);
  background: rgba(108, 163, 255, 0.10);
  color: #fff;
}
.settings-sub-nav__icon,
.setting-title-icon,
.settings-head-icon {
  width: 16px;
  height: 16px;
  display: inline-flex;
  color: var(--primary);
}
.settings-content {
  min-width: 0;
}
.settings-grid {
  display: grid;
  gap: 16px;
}
.section-hd {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 20px;
  font-weight: 800;
  margin-bottom: 14px;
}
.setting-card {
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  background: rgba(14, 18, 24, 0.92);
  padding: 18px;
  box-shadow: 0 12px 30px rgba(0,0,0,0.18);
}
.setting-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 800;
}
.setting-desc {
  margin-top: 8px;
  color: rgba(255,255,255,0.68);
  line-height: 1.45;
}
.setting-row {
  margin-top: 12px;
}
.setting-row-range,
.template-row,
.action-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.range-field {
  min-width: 180px;
  flex: 1;
}
.range-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 700;
  color: rgba(255,255,255,0.7);
}
.range-select {
  width: 100%;
  min-height: 40px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.04);
  color: #fff;
  padding: 0 12px;
}
.btn {
  min-height: 40px;
  border-radius: 10px;
  border: 1px solid rgba(108, 163, 255, 0.4);
  background: rgba(108, 163, 255, 0.14);
  color: #fff;
  padding: 0 14px;
  font-weight: 700;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.btn-ghost {
  background: rgba(255,255,255,0.04);
  border-color: rgba(255,255,255,0.12);
}
.alert {
  border-radius: 12px;
  padding: 12px 14px;
}
.alert-error {
  background: rgba(255, 99, 99, 0.12);
  border: 1px solid rgba(255, 99, 99, 0.22);
  color: #ffd2d2;
}
.alert-success {
  background: rgba(92, 199, 129, 0.12);
  border: 1px solid rgba(92, 199, 129, 0.22);
  color: #d4ffe2;
}
.preview-summary {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}
.preview-summary__line {
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  background: rgba(255,255,255,0.03);
  padding: 10px 12px;
}
.preview-summary__line ul {
  margin: 8px 0 0 18px;
  color: rgba(255,255,255,0.72);
}
.preview-summary__line.ok { color: #c8ffd8; }
.preview-summary__line.warn { color: #ffe5a3; }
.preview-summary__line.info { color: #cfe3ff; }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
@media (max-width: 1023px) {
  .settings-page,
  .settings-page--desktop {
    grid-template-columns: 1fr;
  }
}
</style>
