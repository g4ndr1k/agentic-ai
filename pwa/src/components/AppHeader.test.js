/** @vitest-environment jsdom */

import { beforeAll, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { ref } from 'vue'

const isOnline = ref(true)

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  })
})

vi.mock('../stores/finance.js', () => ({
  useFinanceStore: () => ({
    health: { status: 'ok', transaction_count: 42 },
    reviewCount: 0,
  }),
}))

vi.mock('../composables/useOfflineSync.js', () => ({
  useOfflineSync: () => ({
    isOnline,
  }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    meta: { title: 'Dashboard' },
  }),
}))

import AppHeader from './AppHeader.vue'

describe('AppHeader', () => {
  it('does not render the desktop view toggle in the mobile header', () => {
    isOnline.value = true
    const wrapper = shallowMount(AppHeader)

    expect(wrapper.find('.layout-toggle-btn').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Desktop View')
  })

  it('turns the status dot red when offline without rendering an offline banner message', () => {
    isOnline.value = false
    const wrapper = shallowMount(AppHeader)

    expect(wrapper.find('.status-dot').classes()).not.toContain('ok')
    expect(wrapper.text()).not.toContain("You're offline")
    expect(wrapper.text()).not.toContain('showing last available data')
  })
})
