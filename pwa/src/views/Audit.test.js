/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const transactions = vi.fn()
const wealthSnapshotDates = vi.fn()
const wealthHistory = vi.fn()
const getBalances = vi.fn()
const getHoldings = vi.fn()

const store = {
  dashboardStartMonth: '2026-03',
  dashboardEndMonth: '2026-04',
}

vi.mock('../stores/finance.js', () => ({
  useFinanceStore: () => store,
}))

vi.mock('../api/client.js', () => ({
  api: {
    transactions: (...args) => transactions(...args),
    wealthSnapshotDates: (...args) => wealthSnapshotDates(...args),
    wealthHistory: (...args) => wealthHistory(...args),
    getBalances: (...args) => getBalances(...args),
    getHoldings: (...args) => getHoldings(...args),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import Audit from './Audit.vue'

describe('Audit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    transactions.mockResolvedValue({ total: 0, transactions: [] })
    wealthSnapshotDates.mockResolvedValue(['2026-04-30', '2026-04-06', '2026-03-31'])
    wealthHistory.mockResolvedValue([
      { snapshot_date: '2026-04-06' },
      { snapshot_date: '2026-03-31' },
    ])
    getBalances.mockResolvedValue([])
    getHoldings.mockResolvedValue([])
  })

  it('compares canonical month dates instead of later partial raw dates', async () => {
    mount(Audit)
    await flushPromises()

    expect(getBalances).toHaveBeenNthCalledWith(1, { snapshot_date: '2026-03-31' })
    expect(getBalances).toHaveBeenNthCalledWith(2, { snapshot_date: '2026-04-06' })
    expect(getHoldings).toHaveBeenNthCalledWith(1, { snapshot_date: '2026-03-31' })
    expect(getHoldings).toHaveBeenNthCalledWith(2, { snapshot_date: '2026-04-06' })
  })
})