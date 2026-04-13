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
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    if (isStandalone.value) {
      cacheClear().catch((e) => console.warn('[IDB] cache prune failed:', e.message))
    }
  })

  onUnmounted(() => {
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
  })

  return { isOnline, isStandalone }
}
