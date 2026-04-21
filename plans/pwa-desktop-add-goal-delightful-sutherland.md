# Plan: Add "Goal" View — Passive Income Progress

## Context

The user wants a dedicated Goal view in the PWA that tracks progress toward a Rp 600 million/year passive income target. Passive income = all income **except** the "Earned Income" category (salary/wages). The view should follow the dashboard date range from Settings and visualize monthly + cumulative progress using Chart.js.

---

## What "passive income" means in this codebase

- Transactions with `amount >= 0` and `category NOT IN ('Transfer','Adjustment','Ignored','Opening Balance','Cash Withdrawal')` are income.
- Income categories: `Earned Income`, `Investment Income`, `Interest Income`, `Capital Gains`, `Passive Income`, `Other Income`.
- **Passive income = all income rows where `category !== 'Earned Income'`** — filtered client-side after fetching with `income_only: true`.

---

## Files to modify

| File | Change |
|---|---|
| `pwa/src/router/index.js` | Add `/goal` route between `/transactions` and `/review` |
| `pwa/src/components/DesktopSidebar.vue` | Add `🎯 Goal` link between Transactions and Review |
| `pwa/src/components/BottomNav.vue` | Add `🎯 Goal` link between Txns and Review |

## File to create

| File | Purpose |
|---|---|
| `pwa/src/views/Goal.vue` | New view — fetches income, filters, renders Chart.js chart |

---

## Implementation Details

### 1. Router (`pwa/src/router/index.js`)

Add between the `transactions` and `review` route entries:
```js
const Goal = () => import('../views/Goal.vue')
// ...
{ path: '/goal', name: 'goal', component: Goal, meta: { title: 'Goal', keepAlive: true } },
```

### 2. Desktop Sidebar (`pwa/src/components/DesktopSidebar.vue`)

Insert between Transactions and Review links:
```html
<RouterLink to="/goal" class="desktop-sidebar__link">🎯 <span>Goal</span></RouterLink>
```

### 3. Bottom Nav (`pwa/src/components/BottomNav.vue`)

Insert between Txns and Review links:
```html
<RouterLink to="/goal" class="nav-item">
  <span class="nav-icon">🎯</span>
  <span class="nav-label">Goal</span>
</RouterLink>
```

### 4. Goal View (`pwa/src/views/Goal.vue`)

**Key patterns reused from Dashboard.vue:**
- `import Chart from 'chart.js/auto'` (already installed, v4.4.9)
- `import { useFmt } from '../composables/useFmt.js'` for IDR formatting
- `import { useLayout } from '../composables/useLayout.js'` for desktop/mobile colors
- `api.transactions({ income_only: true, year, month, limit: 1000 })` to fetch income per month

**Data flow:**
1. On mount (and when dashboard range changes), generate a list of YYYY-MM months from `store.dashboardStartMonth` to `store.dashboardEndMonth`.
2. For each month, call `api.transactions({ income_only: true, year, month, limit: 1000 })`.
3. Client-side: for each response, sum `tx.amount` where `tx.category !== 'Earned Income'` → passive income for that month.
4. Compute cumulative total across months.
5. Render two charts with Chart.js:

**Chart 1 — Monthly bar chart (primary)**
- Bars: monthly passive income (green)
- Annotation line: monthly target = 600M / 12 = 50M per month (dashed orange)

**Chart 2 — Cumulative progress line**
- Line: cumulative passive income (green fill)
- Line: prorated goal curve (600M × month_fraction, dashed orange)
- Highlight when cumulative crosses goal

**Summary stats section (above charts):**
- Goal: Rp 600,000,000 / year
- YTD Passive Income: total accumulated
- Monthly average
- % of annual goal achieved
- On track indicator (green ✓ / red behind)

**Constants:**
```js
const GOAL_ANNUAL = 600_000_000  // Rp 600M
const GOAL_MONTHLY = GOAL_ANNUAL / 12  // Rp 50M
const EARNED_INCOME_CAT = 'Earned Income'
const SYSTEM_CATS = new Set(['Transfer', 'Adjustment', 'Ignored', 'Opening Balance', 'Cash Withdrawal'])
```

**Month generation utility:**
```js
function monthsBetween(start, end) {
  // start/end are "YYYY-MM" strings
  // returns array of { year, month, key } objects
}
```

**Chart colors (matching Dashboard.vue pattern):**
```js
const tickColor = isDesktop.value ? '#9db0c9' : '#64748b'
const gridColor = isDesktop.value ? 'rgba(141,162,191,0.12)' : 'rgba(0,0,0,0.04)'
```

---

## Goal constant storage

The `GOAL_ANNUAL = 600_000_000` is hardcoded in the view for now (not user-configurable). This keeps the implementation simple and avoids API changes.

---

## Verification

```bash
cd pwa
npm run dev   # dev server at http://localhost:5173

# Verify:
# 1. Navigate to /goal — view loads without error
# 2. Charts render with bars and goal lines
# 3. Change dashboard range in Settings → Goal view reloads with new months
# 4. Summary stats (YTD total, %, on-track) are accurate
# 5. Desktop sidebar shows 🎯 Goal between Transactions and Review
# 6. Mobile bottom nav shows 🎯 Goal between Txns and Review
# 7. npm run build succeeds

npm run build
```
