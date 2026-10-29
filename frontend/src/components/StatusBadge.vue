<script setup>
import { computed } from 'vue'
const props = defineProps({ state: String })
const styles = {
  running: ['bg-emerald-500/15 text-emerald-300', 'bg-emerald-400', 'Running'],
  starting: ['bg-amber-500/15 text-amber-300', 'bg-amber-400 animate-pulse', 'Starting'],
  stopping: ['bg-amber-500/15 text-amber-300', 'bg-amber-400 animate-pulse', 'Stopping'],
  crashed: ['bg-red-500/15 text-red-300', 'bg-red-400', 'Crashed'],
  stopped: ['bg-slate-500/15 text-slate-300', 'bg-slate-500', 'Stopped'],
}
const s = computed(() => styles[props.state] || styles.stopped)
</script>

<template>
  <span class="chip gap-1.5" :class="s[0]"><span class="h-1.5 w-1.5 rounded-full" :class="s[1]" />{{ s[2] }}</span>
</template>
