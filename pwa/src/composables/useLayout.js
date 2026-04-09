import { ref, computed, onMounted, onUnmounted } from 'vue'

const STORAGE_KEY = 'pwa_layout_mode'

const viewportDesktop = ref(false)
const viewportWideDesktop = ref(false)
const layoutMode = ref('auto')

let mqlDesktop = null
let mqlWide = null
let listenersAttached = false
let mountedCount = 0

function readStoredMode() {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    if (value === 'desktop' || value === 'mobile' || value === 'auto') return value
  } catch {}
  return 'auto'
}

function writeStoredMode(value) {
  try {
    window.localStorage.setItem(STORAGE_KEY, value)
  } catch {}
}

function syncViewportFlags() {
  viewportDesktop.value = !!mqlDesktop?.matches
  viewportWideDesktop.value = !!mqlWide?.matches
}

function onDesktopChange(e) {
  viewportDesktop.value = e.matches
}

function onWideChange(e) {
  viewportWideDesktop.value = e.matches
}

function addListener(mql, handler) {
  if (!mql) return
  if (typeof mql.addEventListener === 'function') mql.addEventListener('change', handler)
  else if (typeof mql.addListener === 'function') mql.addListener(handler)
}

function removeListener(mql, handler) {
  if (!mql) return
  if (typeof mql.removeEventListener === 'function') mql.removeEventListener('change', handler)
  else if (typeof mql.removeListener === 'function') mql.removeListener(handler)
}

function attachListeners() {
  if (listenersAttached) return
  mqlDesktop = window.matchMedia('(min-width: 1024px)')
  mqlWide = window.matchMedia('(min-width: 1440px)')
  syncViewportFlags()
  addListener(mqlDesktop, onDesktopChange)
  addListener(mqlWide, onWideChange)
  listenersAttached = true
}

function detachListeners() {
  if (!listenersAttached) return
  removeListener(mqlDesktop, onDesktopChange)
  removeListener(mqlWide, onWideChange)
  listenersAttached = false
}

export function useLayout() {
  const isDesktop = computed(() => {
    if (layoutMode.value === 'desktop') return true
    if (layoutMode.value === 'mobile') return false
    return viewportDesktop.value
  })

  const isWideDesktop = computed(() => {
    if (!isDesktop.value) return false
    if (layoutMode.value === 'desktop') return true
    return viewportWideDesktop.value
  })

  function setLayoutMode(mode) {
    layoutMode.value = mode
    writeStoredMode(mode)
  }

  function toggleDesktopMode() {
    setLayoutMode(layoutMode.value === 'desktop' ? 'auto' : 'desktop')
  }

  onMounted(() => {
    mountedCount += 1
    layoutMode.value = readStoredMode()
    attachListeners()
  })

  onUnmounted(() => {
    mountedCount = Math.max(0, mountedCount - 1)
    if (mountedCount === 0) detachListeners()
  })

  return {
    isDesktop,
    isWideDesktop,
    layoutMode,
    setLayoutMode,
    toggleDesktopMode,
  }
}
