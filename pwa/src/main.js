import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { registerSW } from 'virtual:pwa-register'
import router from './router/index.js'
import App from './App.vue'
import './style.css'

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

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
