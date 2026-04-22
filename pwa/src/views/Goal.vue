<template>
  <div>
    <div class="page-header">
      <div class="page-title">Investment Income Goal</div>
      <div class="page-subtitle">{{ rangeLabel }}</div>
    </div>

    <div v-if="loading" class="loading">
      <div class="spinner"></div> Loading…
    </div>

    <div v-else-if="error" class="alert alert-error">
      {{ error }}
      <button class="btn btn-sm btn-ghost" style="margin-left:auto" @click="load">Retry</button>
    </div>

    <template v-else>
      <!-- Summary stats -->
      <div class="summary-grid">
        <div class="summary-card">
          <div class="s-label">Annual Goal</div>
          <div class="s-value text-income">{{ fmt(GOAL_ANNUAL) }}</div>
        </div>
        <div class="summary-card">
          <div class="s-label">YTD Investment Income</div>
          <div class="s-value" :class="ytdTotal >= proratedGoal ? 'text-income' : 'text-expense'">
            {{ fmt(ytdTotal) }}
          </div>
        </div>
        <div class="summary-card">
          <div class="s-label">Monthly Average</div>
          <div class="s-value text-neutral">{{ fmt(monthlyAvg) }}</div>
        </div>
        <div class="summary-card">
          <div class="s-label">% of Annual Goal</div>
          <div class="s-value" :class="pctOfGoal >= 100 ? 'text-income' : 'text-expense'">
            {{ pctOfGoal }}%
          </div>
          <div class="s-sub">{{ onTrack ? 'On track' : 'Behind' }}</div>
        </div>
      </div>

      <!-- Monthly bar chart -->
      <div class="card">
        <div class="card-title">Monthly Investment Income vs Target</div>
        <div class="chart-wrap">
          <canvas ref="barRef"></canvas>
        </div>
      </div>

      <!-- Cumulative line chart -->
      <div class="card">
        <div class="card-title">Cumulative Progress</div>
        <div class="chart-wrap">
          <canvas ref="lineRef"></canvas>
        </div>
      </div>

      <!-- Month breakdown table -->
      <div class="card">
        <div class="card-title">Month Breakdown</div>
        <table class="owner-table">
          <thead>
            <tr>
              <th>Month</th>
              <th style="text-align:right">Investment Income</th>
              <th style="text-align:right">Target</th>
              <th style="text-align:right">vs Target</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in monthRows" :key="row.key">
              <td>{{ row.label }}</td>
              <td class="text-income drill-link" @click="goToTransactions(row)">{{ fmt(row.amount) }}</td>
              <td class="text-neutral">{{ fmt(GOAL_MONTHLY) }}</td>
              <td :class="row.amount >= GOAL_MONTHLY ? 'text-income' : 'text-expense'">
                {{ row.amount >= GOAL_MONTHLY ? '+' : '' }}{{ fmt(row.amount - GOAL_MONTHLY) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import Chart from 'chart.js/auto'
import { api } from '../api/client.js'
import { useLayout } from '../composables/useLayout.js'
import { useFinanceStore } from '../stores/finance.js'
import { useFmt } from '../composables/useFmt.js'

const GOAL_ANNUAL = 600_000_000
const GOAL_MONTHLY = GOAL_ANNUAL / 12
const TARGET_CATEGORY = 'Investment Income'
const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

const router = useRouter()
const store = useFinanceStore()
const { isDesktop } = useLayout()
const { fmt } = useFmt()

const barRef = ref(null)
const lineRef = ref(null)
let barChart = null
let lineChart = null

const loading = ref(false)
const error = ref(null)
const monthData = ref([])

function monthsBetween(start, end) {
  // start/end are "YYYY-MM" strings
  const result = []
  let [y, m] = start.split('-').map(Number)
  const [ey, em] = end.split('-').map(Number)
  while (y < ey || (y === ey && m <= em)) {
    result.push({ year: y, month: m, key: `${y}-${String(m).padStart(2, '0')}` })
    if (m === 12) { y++; m = 1 } else m++
  }
  return result
}

const rangeLabel = computed(() => {
  const s = store.dashboardStartMonth || ''
  const e = store.dashboardEndMonth || ''
  if (!s || !e) return ''
  return `${s} → ${e}`
})

const monthRows = computed(() => monthData.value)

const ytdTotal = computed(() => monthData.value.reduce((s, r) => s + r.amount, 0))
const monthlyAvg = computed(() => monthData.value.length ? ytdTotal.value / monthData.value.length : 0)
const pctOfGoal = computed(() => GOAL_ANNUAL > 0 ? Math.round((ytdTotal.value / GOAL_ANNUAL) * 100) : 0)

const proratedGoal = computed(() => {
  const n = monthData.value.length
  return n > 0 ? GOAL_MONTHLY * n : 0
})

const onTrack = computed(() => ytdTotal.value >= proratedGoal.value)

async function load() {
  const start = store.dashboardStartMonth
  const end = store.dashboardEndMonth
  if (!start || !end) return

  loading.value = true
  error.value = null
  destroyCharts()

  try {
    const months = monthsBetween(start, end)
    const results = await Promise.all(
      months.map(({ year, month }) =>
        api.transactions({ category: TARGET_CATEGORY, year, month, limit: 1000 }, { forceFresh: true })
          .then(res => {
            const txns = res?.transactions || []
            const amount = txns
              .filter(tx => (tx.amount ?? 0) >= 0)
              .reduce((s, tx) => s + (tx.amount ?? 0), 0)
            return {
              year,
              month,
              key: `${year}-${String(month).padStart(2, '0')}`,
              label: `${MONTHS_SHORT[month - 1]} ${year}`,
              amount,
            }
          })
      )
    )
    monthData.value = results
    loading.value = false
    await nextTick()
    renderCharts()
  } catch (e) {
    error.value = e.message
    loading.value = false
  }
}

function destroyCharts() {
  if (barChart) { barChart.destroy(); barChart = null }
  if (lineChart) { lineChart.destroy(); lineChart = null }
}

function renderCharts() {
  if (!monthData.value.length) return
  const tickColor = isDesktop.value ? '#9db0c9' : '#64748b'
  const gridColor = isDesktop.value ? 'rgba(141,162,191,0.12)' : 'rgba(0,0,0,0.04)'

  const labels = monthData.value.map(r => r.label)
  const amounts = monthData.value.map(r => r.amount)
  const targets = monthData.value.map(() => GOAL_MONTHLY)

  // Bar chart — monthly passive income vs monthly target
  if (barRef.value) {
    barChart = new Chart(barRef.value, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Investment Income',
            data: amounts,
            backgroundColor: amounts.map(a => a >= GOAL_MONTHLY ? 'rgba(34,197,94,0.75)' : 'rgba(34,197,94,0.45)'),
            borderRadius: 4,
          },
          {
            label: 'Monthly Target',
            data: targets,
            type: 'line',
            borderColor: 'rgba(251,146,60,0.85)',
            borderDash: [6, 3],
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: tickColor, font: { size: 10 }, boxWidth: 10, padding: 10 } },
          tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${fmt(ctx.parsed.y)}` } },
        },
        scales: {
          y: {
            ticks: { color: tickColor, callback: v => fmt(v), font: { size: 9 }, maxTicksLimit: 5 },
            grid: { color: gridColor },
          },
          x: { ticks: { color: tickColor, font: { size: 10 } }, grid: { display: false } },
        },
      },
    })
  }

  // Cumulative line chart
  if (lineRef.value) {
    let cumulative = 0
    const cumulativeAmounts = amounts.map(a => { cumulative += a; return cumulative })
    const cumulativeGoal = amounts.map((_, i) => GOAL_MONTHLY * (i + 1))

    lineChart = new Chart(lineRef.value, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Cumulative Investment Income',
            data: cumulativeAmounts,
            borderColor: 'rgba(34,197,94,0.9)',
            backgroundColor: 'rgba(34,197,94,0.12)',
            fill: true,
            tension: 0.3,
            pointRadius: 4,
            pointBackgroundColor: cumulativeAmounts.map((v, i) =>
              v >= cumulativeGoal[i] ? 'rgba(34,197,94,1)' : 'rgba(239,68,68,0.8)'
            ),
          },
          {
            label: 'Prorated Goal',
            data: cumulativeGoal,
            borderColor: 'rgba(251,146,60,0.85)',
            borderDash: [6, 3],
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
            tension: 0.1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: tickColor, font: { size: 10 }, boxWidth: 10, padding: 10 } },
          tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${fmt(ctx.parsed.y)}` } },
        },
        scales: {
          y: {
            ticks: { color: tickColor, callback: v => fmt(v), font: { size: 9 }, maxTicksLimit: 5 },
            grid: { color: gridColor },
          },
          x: { ticks: { color: tickColor, font: { size: 10 } }, grid: { display: false } },
        },
      },
    })
  }
}

function goToTransactions(row) {
  router.push({
    path: '/transactions',
    query: { year: row.year, month: row.month, category: TARGET_CATEGORY },
  })
}

onMounted(load)
watch([() => store.dashboardStartMonth, () => store.dashboardEndMonth], load)
onUnmounted(destroyCharts)
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 800;
  color: var(--text);
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 2px;
}

.chart-wrap {
  height: 240px;
}

.drill-link {
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
  text-decoration-style: dotted;
}

.drill-link:hover {
  opacity: 0.75;
}

@media (min-width: 1024px) {
  .chart-wrap {
    height: 300px;
  }

  .summary-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}
</style>
