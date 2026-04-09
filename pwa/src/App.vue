<script setup>
import { computed, onMounted } from 'vue'
import { useFinanceStore } from './stores/finance.js'
import { useLayout } from './composables/useLayout.js'
import MobileShell from './layouts/MobileShell.vue'
import DesktopShell from './layouts/DesktopShell.vue'

const store = useFinanceStore()
const { isDesktop } = useLayout()

onMounted(() => store.bootstrap())

const shell = computed(() => (isDesktop.value ? DesktopShell : MobileShell))
</script>

<template>
  <component :is="shell" />
</template>
