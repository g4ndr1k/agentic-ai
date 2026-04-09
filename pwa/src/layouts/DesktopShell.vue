<script setup>
import DesktopSidebar from '../components/DesktopSidebar.vue'
</script>

<template>
  <div class="desktop-shell">
    <DesktopSidebar />
    <main class="desktop-content">
      <RouterView />
    </main>
  </div>
</template>
