/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Chart from 'chart.js/auto'

const store = {
  dashboardStartMonth: '2026-01',
  dashboardEndMonth: '2026-03',
  dashboardRangeLabel: 'Jan 2026 – Mar 2026',
}

const summaryMonth = vi.fn()
const wealthHistory = vi.fn()
const getHoldings = vi.fn()
const chartDestroy = vi.fn()

vi.mock('chart.js/auto', () => ({
  default: vi.fn().mockImplementation(() => ({
    destroy: chartDestroy,
  })),
}))

vi.mock('../stores/finance.js', () => ({
  useFinanceStore: () => store,
}))

vi.mock('../api/client.js', () => ({
  api: {
    wealthSummary: vi.fn(async () => ({ ok: true })),
    wealthHistory: (...args) => wealthHistory(...args),
    getHoldings: (...args) => getHoldings(...args),
    summaryMonth: (...args) => summaryMonth(...args),
  },
}))

import MainDashboard from './MainDashboard.vue'

beforeEach(() => {
  vi.clearAllMocks()
  chartDestroy.mockClear()
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
    createLinearGradient: () => ({ addColorStop: vi.fn() }),
  }))

  wealthHistory.mockResolvedValue([
    {
      snapshot_date: '2026-01-31',
      net_worth_idr: 900000000,
      total_assets_idr: 1000000000,
      total_liabilities_idr: 100000000,
      savings_idr: 250000000,
      checking_idr: 50000000,
      money_market_idr: 0,
      physical_cash_idr: 0,
      bonds_idr: 100000000,
      stocks_idr: 200000000,
      mutual_funds_idr: 150000000,
      retirement_idr: 50000000,
      crypto_idr: 25000000,
      real_estate_idr: 100000000,
      vehicles_idr: 50000000,
      gold_idr: 25000000,
      other_assets_idr: 50000000,
    },
    {
      snapshot_date: '2026-02-28',
      net_worth_idr: 980000000,
      total_assets_idr: 1080000000,
      total_liabilities_idr: 100000000,
      savings_idr: 260000000,
      checking_idr: 60000000,
      money_market_idr: 0,
      physical_cash_idr: 0,
      bonds_idr: 110000000,
      stocks_idr: 220000000,
      mutual_funds_idr: 160000000,
      retirement_idr: 50000000,
      crypto_idr: 30000000,
      real_estate_idr: 110000000,
      vehicles_idr: 50000000,
      gold_idr: 30000000,
      other_assets_idr: 60000000,
    },
    {
      snapshot_date: '2026-03-31',
      net_worth_idr: 1050000000,
      total_assets_idr: 1150000000,
      total_liabilities_idr: 100000000,
      savings_idr: 280000000,
      checking_idr: 70000000,
      money_market_idr: 0,
      physical_cash_idr: 0,
      bonds_idr: 120000000,
      stocks_idr: 230000000,
      mutual_funds_idr: 170000000,
      retirement_idr: 50000000,
      crypto_idr: 30000000,
      real_estate_idr: 120000000,
      vehicles_idr: 50000000,
      gold_idr: 30000000,
      other_assets_idr: 50000000,
    },
  ])

  getHoldings.mockResolvedValue([])

  summaryMonth
    .mockResolvedValueOnce({ total_income: 100000000, total_expense: -70000000 })
    .mockResolvedValueOnce({ total_income: 110000000, total_expense: -75000000 })
    .mockResolvedValueOnce({ total_income: 120000000, total_expense: -80000000 })
})

describe('MainDashboard', () => {
  it('renders asset allocation above assets over time and uses a canvas for cash flow', async () => {
    const wrapper = mount(MainDashboard, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await flushPromises()

    const titles = wrapper.findAll('.dash-card__title').map((node) => node.text())
    expect(titles).toEqual([
      'Asset Allocation',
      'Assets Over Time',
      'Cash Flow Summary',
    ])

    expect(wrapper.find('.dash-card--alloc canvas').exists()).toBe(true)
    expect(wrapper.find('.dash-card--alloc svg').exists()).toBe(false)
    expect(wrapper.findAll('.dash-card--alloc .dash-kpi')).toHaveLength(4)
    expect(wrapper.find('.dash-card--wealth canvas').exists()).toBe(true)
    expect(wrapper.find('.dash-card--wealth svg').exists()).toBe(false)
    expect(wrapper.find('.dash-card--flows canvas').exists()).toBe(true)
    expect(wrapper.find('.dash-card--flows svg').exists()).toBe(false)
    expect(Chart).toHaveBeenCalledTimes(3)
  })
})
