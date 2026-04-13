# Offline-First PWA Architecture — Implementation Plan

## Context

This is a Vue 3 + Vite finance dashboard PWA (`/pwa`). It already has `vite-plugin-pwa` (Workbox) configured with a basic `NetworkFirst` strategy and standard SW registration. The goal is to harden it for **iOS Safari offline-first use** — covering cache strategy, IndexedDB persistence, an offline indicator, and a reliable online-event-driven sync queue.

---

## 1. Install Dependencies

```bash
cd pwa
npm install idb
```

> `idb` is a lightweight (~1KB) promise wrapper around IndexedDB. No need for Dexie — `idb` is sufficient and has zero extra deps.

---

## 2. `index.html` — iOS Meta Tags & Apple Touch Icon

**File:** `pwa/index.html`

Add inside `<head>` (missing items only):

```html
<!-- Apple Touch Icon (required for crisp home-screen icon on iOS) -->
<link rel="apple-touch-icon" href="/icons/icon-192.png" />

<!-- Splash screen support -->
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
```

> `apple-mobile-web-app-capable` and `apple-mobile-web-app-title` are already present. The missing piece is `apple-touch-icon` — without it iOS uses a blurry screenshot.

---

## 3. `vite.config.js` — Workbox Stale-While-Revalidate + Custom SW

**File:** `pwa/vite.config.js`

Replace the `workbox` block:

```js
workbox: {
  clientsClaim: true,
  skipWaiting: true,

  // Point to a custom SW for lifecycle debug logging
  // (vite-plugin-pwa will inject Workbox precaching into this file)
  // Use injectManifest mode instead of generateSW:
},
```

Switch `VitePWA` to `injectManifest` strategy so we can write a custom `sw.js` with logging:

```js
VitePWA({
  registerType: 'autoUpdate',
  strategies: 'injectManifest',   // <-- changed from default generateSW
  srcDir: 'src',
  filename: 'sw.js',
  manifest: { /* keep existing manifest block unchanged */ },
})
```

> With `injectManifest`, Workbox injects the precache manifest into your own `sw.js`, giving you full control for logging and custom caching.

---

## 4. `src/sw.js` — Custom Service Worker

**File:** `pwa/src/sw.js` *(new file)*

```js
import { clientsClaim } from 'workbox-core'
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching'
import { registerRoute } from 'workbox-routing'
import { StaleWhileRevalidate, NetworkFirst } from 'workbox-strategies'
import { ExpirationPlugin } from 'workbox-expiration'
import { CacheableResponsePlugin } from 'workbox-cacheable-response'

// ── Lifecycle Debug Logging (visible in Safari Web Inspector > Console) ──────
console.log('[SW] Installing service worker...')

self.addEventListener('install', (event) => {
  console.log('[SW] install event fired')
})

self.addEventListener('activate', (event) => {
  console.log('[SW] activate event fired — now controlling all clients')
})

self.addEventListener('fetch', (event) => {
  // Log only API fetches to avoid noise
  if (event.request.url.includes('/api/')) {
    console.log('[SW] fetch intercepted:', event.request.method, event.request.url)
  }
})

// ── Workbox Setup ─────────────────────────────────────────────────────────────
clientsClaim()
self.__WB_DISABLE_DEV_LOGS = false   // keep Workbox logs in dev

cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)   // injected by vite-plugin-pwa

// ── Static Assets: Stale-While-Revalidate ────────────────────────────────────
registerRoute(
  ({ request }) =>
    request.destination === 'style' ||
    request.destination === 'script' ||
    request.destination === 'image' ||
    request.destination === 'font',
  new StaleWhileRevalidate({
    cacheName: 'static-assets',
    plugins: [
      new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 7 * 24 * 60 * 60 }),
      new CacheableResponsePlugin({ statuses: [0, 200] }),
    ],
  })
)

// ── API Calls: Stale-While-Revalidate (read endpoints) ───────────────────────
registerRoute(
  ({ url }) =>
    url.pathname.startsWith('/api/') &&
    !url.pathname.endsWith('/sync') &&
    !url.pathname.endsWith('/import') &&
    !url.pathname.endsWith('/alias') &&
    !url.pathname.startsWith('/api/ai/'),
  new StaleWhileRevalidate({
    cacheName: 'api-cache',
    plugins: [
      new ExpirationPlugin({ maxEntries: 60, maxAgeSeconds: 10 * 60 }),
      new CacheableResponsePlugin({ statuses: [0, 200] }),
    ],
  })
)

// ── Mutation & AI Endpoints: NetworkFirst (never serve stale) ─────────────────
registerRoute(
  ({ url }) =>
    url.pathname.endsWith('/sync') ||
    url.pathname.endsWith('/import') ||
    url.pathname.endsWith('/alias') ||
    url.pathname.startsWith('/api/ai/'),
  new NetworkFirst({
    cacheName: 'mutations-cache',
    networkTimeoutSeconds: 10,
    plugins: [
      new CacheableResponsePlugin({ statuses: [0, 200] }),
    ],
  })
)

// ── Cache Cleanup: Enforce 50MB budget ───────────────────────────────────────
// Purge api-cache entries when storage > 45MB (leaving headroom)
async function enforceStorageQuota() {
  if (!navigator.storage?.estimate) return
  const { usage, quota } = await navigator.storage.estimate()
  const LIMIT = 45 * 1024 * 1024  // 45MB
  if (usage > LIMIT) {
    console.log('[SW] Storage quota exceeded — pruning api-cache')
    const cache = await caches.open('api-cache')
    const keys  = await cache.keys()
    // Delete oldest 20%
    const toPrune = Math.ceil(keys.length * 0.2)
    for (let i = 0; i < toPrune; i++) await cache.delete(keys[i])
    console.log(`[SW] Pruned ${toPrune} cache entries`)
  }
}

self.addEventListener('activate', (event) => {
  event.waitUntil(enforceStorageQuota())
})
```

---

## 5. `src/db/index.js` — IndexedDB Schema via `idb`

**File:** `pwa/src/db/index.js` *(new file)*

```js
import { openDB } from 'idb'

const DB_NAME = 'finance-app'
const DB_VERSION = 1

export const db = openDB(DB_NAME, DB_VERSION, {
  upgrade(db) {
    // Reference data snapshots
    if (!db.objectStoreNames.contains('cache')) {
      const store = db.createObjectStore('cache', { keyPath: 'key' })
      store.createIndex('updatedAt', 'updatedAt')
    }

    // Offline mutation queue (failed POSTs/PATCHes/DELETEs to retry on reconnect)
    if (!db.objectStoreNames.contains('syncQueue')) {
      const q = db.createObjectStore('syncQueue', { keyPath: 'id', autoIncrement: true })
      q.createIndex('createdAt', 'createdAt')
    }
  },
})

// ── Cache helpers ─────────────────────────────────────────────────────────────
export async function cacheSet(key, value) {
  const conn = await db
  await conn.put('cache', { key, value, updatedAt: Date.now() })
}

export async function cacheGet(key) {
  const conn = await db
  const entry = await conn.get('cache', key)
  return entry?.value ?? null
}

export async function cacheClear(maxAgeMs = 24 * 60 * 60 * 1000) {
  // Remove entries older than maxAgeMs
  const conn = await db
  const cutoff = Date.now() - maxAgeMs
  const tx = conn.transaction('cache', 'readwrite')
  let cursor = await tx.store.index('updatedAt').openCursor()
  let pruned = 0
  while (cursor && cursor.value.updatedAt < cutoff) {
    await cursor.delete()
    pruned++
    cursor = await cursor.continue()
  }
  await tx.done
  console.log(`[IDB] Pruned ${pruned} stale cache entries`)
}

// ── Sync queue helpers ────────────────────────────────────────────────────────
export async function queueMutation(method, url, body) {
  const conn = await db
  await conn.add('syncQueue', { method, url, body, createdAt: Date.now() })
  console.log('[IDB] Queued mutation:', method, url)
}

export async function drainSyncQueue() {
  const conn = await db
  const all  = await conn.getAll('syncQueue')
  if (!all.length) return
  console.log(`[IDB] Draining ${all.length} queued mutations...`)

  for (const item of all) {
    try {
      const res = await fetch(item.url, {
        method: item.method,
        headers: { 'Content-Type': 'application/json' },
        body: item.body ? JSON.stringify(item.body) : undefined,
      })
      if (res.ok) {
        await conn.delete('syncQueue', item.id)
        console.log('[IDB] Synced and removed queued item:', item.id)
      }
    } catch (e) {
      console.warn('[IDB] Sync retry failed for item', item.id, e.message)
    }
  }
}
```

---

## 6. `src/composables/useOfflineSync.js` — Online Event Watcher

**File:** `pwa/src/composables/useOfflineSync.js` *(new file)*

```js
import { ref, onMounted, onUnmounted } from 'vue'
import { drainSyncQueue, cacheClear } from '../db/index.js'

export function useOfflineSync(onReconnect) {
  const isOnline = ref(navigator.onLine)
  const isStandalone = ref(
    window.navigator.standalone === true ||
    window.matchMedia('(display-mode: standalone)').matches
  )

  async function handleOnline() {
    console.log('[Sync] Back online — triggering sync')
    isOnline.value = true
    await drainSyncQueue()
    if (onReconnect) await onReconnect()
  }

  function handleOffline() {
    console.log('[Sync] Gone offline')
    isOnline.value = false
  }

  onMounted(() => {
    window.addEventListener('online',  handleOnline)
    window.addEventListener('offline', handleOffline)

    // Run maintenance on mount if running from home screen
    if (isStandalone.value) {
      cacheClear()  // prune IDB entries older than 24h
    }
  })

  onUnmounted(() => {
    window.removeEventListener('online',  handleOnline)
    window.removeEventListener('offline', handleOffline)
  })

  return { isOnline, isStandalone }
}
```

---

## 7. `src/components/OfflineStatus.vue` — Global Offline Indicator

**File:** `pwa/src/components/OfflineStatus.vue` *(new file)*

```vue
<script setup>
import { useOfflineSync } from '../composables/useOfflineSync.js'
import { useFinanceStore } from '../stores/finance.js'

const store = useFinanceStore()
const { isOnline, isStandalone } = useOfflineSync(() => store.bootstrap())
</script>

<template>
  <Transition name="offline-slide">
    <div v-if="!isOnline" class="offline-banner" role="alert" aria-live="assertive">
      <span class="offline-icon">⚡</span>
      <span>You're offline — showing last available data</span>
    </div>
  </Transition>
</template>

<style scoped>
.offline-banner {
  position: fixed;
  top: env(safe-area-inset-top, 0);
  left: 0;
  right: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #f59e0b;
  color: #1c1917;
  font-size: 14px;
  font-weight: 600;
  text-align: center;
  justify-content: center;
}

.offline-icon { font-size: 16px; }

/* Slide down on appear, slide up on leave */
.offline-slide-enter-active,
.offline-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.offline-slide-enter-from,
.offline-slide-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}
</style>
```

---

## 8. Mount `OfflineStatus` in `MobileShell.vue` and `DesktopShell.vue`

**File:** `pwa/src/layouts/MobileShell.vue`

```vue
<script setup>
import AppHeader from '../components/AppHeader.vue'
import BottomNav from '../components/BottomNav.vue'
import OfflineStatus from '../components/OfflineStatus.vue'  // add
</script>

<template>
  <div class="app">
    <OfflineStatus />   <!-- add at top of app -->
    <AppHeader />
    <main class="content">
      <RouterView />
    </main>
    <BottomNav />
  </div>
</template>
```

Apply the same import + `<OfflineStatus />` to `pwa/src/layouts/DesktopShell.vue`.

---

## 9. `main.js` — SW Registration with Lifecycle Logging

**File:** `pwa/src/main.js`

Update `registerSW` block to log lifecycle events:

```js
const updateSW = registerSW({
  immediate: true,
  onNeedRefresh() {
    console.log('[SW] New version available — auto-updating')
    updateSW(true)
  },
  onOfflineReady() {
    console.log('[SW] App is ready to work offline')
  },
  onRegistered(registration) {
    console.log('[SW] Service worker registered:', registration?.scope)
  },
  onRegisterError(error) {
    console.error('[SW] Service worker registration failed:', error)
  },
})
```

---

## Critical Files Summary

| File | Action |
|---|---|
| `pwa/index.html` | Add `apple-touch-icon` link tag |
| `pwa/vite.config.js` | Switch to `injectManifest` strategy, point to `src/sw.js` |
| `pwa/src/sw.js` | **New** — custom SW with SWR strategy + lifecycle logs + cache cleanup |
| `pwa/src/db/index.js` | **New** — IndexedDB schema (cache store + syncQueue) |
| `pwa/src/composables/useOfflineSync.js` | **New** — online event watcher + drain queue on reconnect |
| `pwa/src/components/OfflineStatus.vue` | **New** — offline banner with slide transition |
| `pwa/src/layouts/MobileShell.vue` | Add `<OfflineStatus />` |
| `pwa/src/layouts/DesktopShell.vue` | Add `<OfflineStatus />` |
| `pwa/src/main.js` | Expand `registerSW` callbacks with console logs |

---

## Verification

1. **Build and serve**: `npm run build && npm run preview` — check DevTools → Application → Service Workers shows the new SW registered.
2. **iOS Safari**: Open in Safari → Share → Add to Home Screen. Confirm icon is crisp (not a blurry screenshot).
3. **Offline test**: In DevTools → Network → set "Offline". Reload — app should load from cache. Offline banner should appear.
4. **Reconnect test**: Toggle back online — check console for `[Sync] Back online — triggering sync` and `[IDB] Draining` logs.
5. **Safari Web Inspector**: Connect iPhone to Mac → Develop → iPhone → SW logs should show `[SW] install`, `[SW] activate`, `[SW] fetch intercepted:` for API calls.
6. **Storage estimate**: In console: `navigator.storage.estimate().then(console.log)` — confirm `usage < quota`.
