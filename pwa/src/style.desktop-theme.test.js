/** @vitest-environment node */

import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const styleCss = readFileSync(resolve(__dirname, './style.css'), 'utf8')

describe('desktop theme consistency styles', () => {
  it('applies dashboard-style desktop overrides to shared controls across non-dashboard views', () => {
    expect(styleCss).toContain('.desktop-shell .btn-primary')
    expect(styleCss).toContain('.desktop-shell .audit-tab.active')
    expect(styleCss).toContain('.desktop-shell .group-tab.active')
    expect(styleCss).toContain('.desktop-shell .form-type-tab.active')
    expect(styleCss).toContain('.desktop-shell .wealth-fab')
    expect(styleCss).toContain('.desktop-shell .holdings-fab')
    expect(styleCss).toContain('.desktop-shell .ro-notice')
    expect(styleCss).toContain('.desktop-shell .price-badge.stock-price')
    expect(styleCss).toContain('.desktop-shell .cb-fill')
  })
})
