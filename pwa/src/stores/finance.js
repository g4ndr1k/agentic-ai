import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { api } from '../api/client.js'
import { cacheGet, cacheSet } from '../db/index.js'

const DASHBOARD_MIN_MONTH = '2026-01'
const DASHBOARD_START_KEY = 'finance.dashboard.startMonth'
const DASHBOARD_END_KEY = 'finance.dashboard.endMonth'
const REPORTING_START_KEY = 'finance.reporting.startMonth'
const REPORTING_END_KEY = 'finance.reporting.endMonth'
const AUTO_AI_REFINE_KEY = 'finance.autoAiRefine'
const HIDE_NUMBERS_KEY = 'finance.hideNumbers'
const CACHE_KEYS = {
  health: 'finance.health',
  owners: 'finance.owners',
  accounts: 'finance.accounts',
  categories: 'finance.categories',
  years: 'finance.years',
}

function safeStorageGet(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeStorageSet(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // ignore storage failures
  }
}

function _getCurrentMonthKey() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function normalizeDashboardMonth(value, fallback) {
  if (!/^\d{4}-\d{2}$/.test(value || '')) return fallback
  if (value < DASHBOARD_MIN_MONTH) return DASHBOARD_MIN_MONTH
  const upperBound = _getCurrentMonthKey()
  if (value > upperBound) return upperBound
  return value
}

// Debounce helper — coalesces rapid calls within *ms* milliseconds.
function debounce(fn, ms) {
  let timer = null
  return (...args) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), ms)
  }
}

export const useFinanceStore = defineStore('finance', () => {
  const owners = ref([])
  const accounts = ref([])
  const categories = ref([])
  const years = ref([])
  const health = ref(null)
  const reviewCount = ref(0)
  const isReadOnly = ref(false)
  const autoAiRefine = ref(safeStorageGet(AUTO_AI_REFINE_KEY) !== 'false')
  const hideNumbers = ref(safeStorageGet(HIDE_NUMBERS_KEY) === 'true')

  const now = new Date()
  const currentMonthKey = computed(() => _getCurrentMonthKey())
  const dashboardStartMonth = ref(normalizeDashboardMonth(safeStorageGet(DASHBOARD_START_KEY), DASHBOARD_MIN_MONTH))
  const dashboardEndMonth = ref(normalizeDashboardMonth(safeStorageGet(DASHBOARD_END_KEY), currentMonthKey.value))
  const reportingStartMonth = ref(normalizeDashboardMonth(safeStorageGet(REPORTING_START_KEY), DASHBOARD_MIN_MONTH))
  const reportingEndMonth = ref(normalizeDashboardMonth(safeStorageGet(REPORTING_END_KEY), currentMonthKey.value))
  // Eagerly persist so defaults are always in localStorage (watchers only fire on change)
  safeStorageSet(DASHBOARD_START_KEY, dashboardStartMonth.value)
  safeStorageSet(DASHBOARD_END_KEY, dashboardEndMonth.value)
  safeStorageSet(REPORTING_START_KEY, reportingStartMonth.value)
  safeStorageSet(REPORTING_END_KEY, reportingEndMonth.value)

  // Clamp selectedYear/selectedMonth to dashboard range end on init
  const _initEnd = dashboardEndMonth.value || currentMonthKey.value
  const [_ey, _em] = _initEnd.split('-').map(Number)
  const selectedYear = ref(_ey || now.getFullYear())
  const selectedMonth = ref(_em || (now.getMonth() + 1))
  const selectedOwner = ref('')

  const categoryMap = computed(() => {
    const m = {}
    for (const c of categories.value) m[c.category] = c
    return m
  })

  const categoryNames = computed(() =>
    categories.value
      .slice()
      .sort((a, b) => a.sort_order - b.sort_order)
      .map(c => c.category)
  )

  const dashboardMonthOptions = computed(() => {
    const [startYear, startMonth] = DASHBOARD_MIN_MONTH.split('-').map(Number)
    const [endYear, endMonth] = currentMonthKey.value.split('-').map(Number)
    const options = []
    const cursor = new Date(startYear, startMonth - 1, 1)
    const end = new Date(endYear, endMonth - 1, 1)
    const labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    while (cursor <= end) {
      const year = cursor.getFullYear()
      const month = cursor.getMonth() + 1
      const value = `${year}-${String(month).padStart(2, '0')}`
      options.push({ value, label: `${labels[month - 1]} ${year}` })
      cursor.setMonth(cursor.getMonth() + 1)
    }
    return options
  })

  const dashboardRangeLabel = computed(() => {
    const lookup = new Map(dashboardMonthOptions.value.map(option => [option.value, option.label]))
    return `${lookup.get(dashboardStartMonth.value) || dashboardStartMonth.value} - ${lookup.get(dashboardEndMonth.value) || dashboardEndMonth.value}`
  })

  const reportingRangeLabel = computed(() => {
    const lookup = new Map(dashboardMonthOptions.value.map(option => [option.value, option.label]))
    return `${lookup.get(reportingStartMonth.value) || reportingStartMonth.value} - ${lookup.get(reportingEndMonth.value) || reportingEndMonth.value}`
  })

  async function loadCachedResource(cacheKey, fetcher, applyValue, options = {}) {
    try {
      const fresh = await fetcher(options)
      applyValue(fresh)
      await cacheSet(cacheKey, fresh)
      return fresh
    } catch (e) {
      const cached = await cacheGet(cacheKey)
      if (cached !== null) {
        console.warn(`[Cache] Using cached ${cacheKey}:`, e.message)
        applyValue(cached)
        return cached
      }
      console.warn(`${cacheKey} load failed:`, e.message)
      throw e
    }
  }

  async function loadHealth(options = {}) {
    try {
      await loadCachedResource(CACHE_KEYS.health, (requestOptions) => api.health(requestOptions), (value) => {
        health.value = value
        reviewCount.value = value?.needs_review ?? 0
        isReadOnly.value = value?.read_only === true
        if (isReadOnly.value && safeStorageGet(HIDE_NUMBERS_KEY) === null) {
          hideNumbers.value = true
        }
      }, options)
    } catch {
      // no cached fallback available
    }
  }

  async function loadOwners(options = {}) {
    try {
      await loadCachedResource(CACHE_KEYS.owners, (requestOptions) => api.owners(requestOptions), (value) => {
        owners.value = value
      }, options)
    } catch {
      // no cached fallback available
    }
  }

  async function loadAccounts(options = {}) {
    try {
      await loadCachedResource(CACHE_KEYS.accounts, (requestOptions) => api.accounts(requestOptions), (value) => {
        accounts.value = value
      }, options)
    } catch {
      // no cached fallback available
    }
  }

  async function loadCategories(options = {}) {
    try {
      await loadCachedResource(CACHE_KEYS.categories, (requestOptions) => api.categories(requestOptions), (value) => {
        categories.value = [...value].sort((a, b) => a.sort_order - b.sort_order)
      }, options)
    } catch {
      // no cached fallback available
    }
  }

  async function loadYears(options = {}) {
    try {
      await loadCachedResource(CACHE_KEYS.years, (requestOptions) => api.summaryYears(requestOptions), (value) => {
        years.value = value
      }, options)
    } catch {
      // no cached fallback available
    }
  }

  function decrementReviewCount(n = 1) {
    reviewCount.value = Math.max(0, reviewCount.value - n)
  }

  function setReviewCount(n) {
    reviewCount.value = Math.max(0, n)
  }

  // ── Server-side preference persistence ────────────────────────────────────
  // Debounced save: coalesces rapid start+end changes into a single PUT.
  const _savePrefsToServer = debounce(async () => {
    try {
      await api.savePreferences({
        dashboard_start_month: dashboardStartMonth.value,
        dashboard_end_month: dashboardEndMonth.value,
      })
    } catch (e) {
      // Non-critical — localStorage is the local fallback
      console.warn('[Preferences] Server save failed:', e.message)
    }
  }, 500)

  function setDashboardRange(startMonth, endMonth) {
    const normalizedStart = normalizeDashboardMonth(startMonth, DASHBOARD_MIN_MONTH)
    const normalizedEnd = normalizeDashboardMonth(endMonth, currentMonthKey.value)
    if (normalizedStart <= normalizedEnd) {
      dashboardStartMonth.value = normalizedStart
      dashboardEndMonth.value = normalizedEnd
    } else {
      dashboardStartMonth.value = normalizedEnd
      dashboardEndMonth.value = normalizedStart
    }
    _savePrefsToServer()
  }

  function setReportingRange(startMonth, endMonth) {
    const normalizedStart = normalizeDashboardMonth(startMonth, DASHBOARD_MIN_MONTH)
    const normalizedEnd = normalizeDashboardMonth(endMonth, currentMonthKey.value)
    if (normalizedStart <= normalizedEnd) {
      reportingStartMonth.value = normalizedStart
      reportingEndMonth.value = normalizedEnd
    } else {
      reportingStartMonth.value = normalizedEnd
      reportingEndMonth.value = normalizedStart
    }
  }

  watch(dashboardStartMonth, (value) => {
    safeStorageSet(DASHBOARD_START_KEY, value)
    if (value > dashboardEndMonth.value) dashboardEndMonth.value = value
  })

  watch(dashboardEndMonth, (value) => {
    safeStorageSet(DASHBOARD_END_KEY, value)
    if (value < dashboardStartMonth.value) dashboardStartMonth.value = value
  })

  watch(reportingStartMonth, (value) => {
    safeStorageSet(REPORTING_START_KEY, value)
    if (value > reportingEndMonth.value) reportingEndMonth.value = value
  })

  watch(reportingEndMonth, (value) => {
    safeStorageSet(REPORTING_END_KEY, value)
    if (value < reportingStartMonth.value) reportingStartMonth.value = value
  })

  async function _loadServerPreferences() {
    try {
      const prefs = await api.preferences()
      const srvStart = normalizeDashboardMonth(prefs.dashboard_start_month, null)
      const srvEnd = normalizeDashboardMonth(prefs.dashboard_end_month, null)
      if (srvStart) dashboardStartMonth.value = srvStart
      if (srvEnd) dashboardEndMonth.value = srvEnd
    } catch {
      // Server unavailable — keep localStorage values
    }
  }

  async function bootstrap(options = {}) {
    // Load server preferences first so dashboard range is authoritative
    await _loadServerPreferences()
    await Promise.all([loadHealth(options), loadOwners(options), loadAccounts(options), loadCategories(options), loadYears(options)])
  }

  function setAutoAiRefine(value) {
    autoAiRefine.value = value
    safeStorageSet(AUTO_AI_REFINE_KEY, String(value))
  }

  function setHideNumbers(value) {
    hideNumbers.value = value
    safeStorageSet(HIDE_NUMBERS_KEY, String(value))
  }

  return {
    owners, accounts, categories, years, health, reviewCount, isReadOnly, autoAiRefine,
    selectedYear, selectedMonth, selectedOwner,
    dashboardStartMonth, dashboardEndMonth, reportingStartMonth, reportingEndMonth,
    categoryMap, categoryNames, dashboardMonthOptions, dashboardRangeLabel, reportingRangeLabel,
    loadHealth, loadOwners, loadAccounts, loadCategories, loadYears,
    decrementReviewCount, setReviewCount, setDashboardRange, setReportingRange, setAutoAiRefine, setHideNumbers, bootstrap,
    hideNumbers,
  }
})
