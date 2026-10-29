<script setup>
import { store } from '../store'
const colors = { info: 'border-sky-500/40', success: 'border-emerald-500/50', error: 'border-red-500/60' }
</script>

<template>
  <div class="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
    <TransitionGroup name="toast">
      <div v-for="t in store.toasts" :key="t.id" class="card pointer-events-auto border-l-4 px-4 py-3 text-sm shadow-xl" :class="colors[t.kind]">
        {{ t.message }}
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: all 0.2s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(20px); }
</style>
