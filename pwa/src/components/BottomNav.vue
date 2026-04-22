<script setup>
import { useFinanceStore } from '../stores/finance.js'

const store = useFinanceStore()
</script>

<template>
  <nav class="bottom-nav">
    <RouterLink to="/" class="nav-item">Dashboard</RouterLink>
    <RouterLink to="/flows" class="nav-item">Flows</RouterLink>
    <RouterLink to="/wealth" class="nav-item">Wealth</RouterLink>
    <RouterLink to="/transactions" class="nav-item">Txns</RouterLink>
    <RouterLink to="/settings" class="nav-item nav-item--more">
      More
      <span v-if="store.reviewCount > 0" class="nav-dot"></span>
    </RouterLink>
  </nav>
</template>
