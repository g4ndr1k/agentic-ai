<script setup>
import AppHeader from '../components/AppHeader.vue'
import BottomNav from '../components/BottomNav.vue'
</script>

<template>
  <div class="app">
    <AppHeader />
    <main class="content">
      <RouterView />
    </main>
    <BottomNav />
  </div>
</template>
