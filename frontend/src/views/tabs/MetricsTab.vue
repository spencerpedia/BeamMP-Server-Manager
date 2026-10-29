<script setup>
import { computed, inject } from 'vue'
import { bytes } from '../../format'
import LineChart from '../../components/LineChart.vue'

const server = inject('server')
const live = inject('live')
const labels = computed(() => live.stats.map((p) => new Date(p.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })))
const latest = computed(() => live.stats[live.stats.length - 1])
const peak = (key) => Math.max(0, ...live.stats.map((p) => p[key]))
</script>

<template>
  <div class="space-y-4">
    <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <div class="card p-4"><div class="text-xs uppercase text-slate-400">CPU now</div><div class="mt-1 text-xl font-bold">{{ latest ? `${latest.cpu}%` : '–' }}</div></div>
      <div class="card p-4"><div class="text-xs uppercase text-slate-400">RAM now</div><div class="mt-1 text-xl font-bold">{{ latest ? bytes(latest.mem) : '–' }}</div></div>
      <div class="card p-4"><div class="text-xs uppercase text-slate-400">Peak RAM</div><div class="mt-1 text-xl font-bold">{{ live.stats.length ? bytes(peak('mem')) : '–' }}</div></div>
      <div class="card p-4"><div class="text-xs uppercase text-slate-400">Peak players</div><div class="mt-1 text-xl font-bold">{{ live.stats.length ? peak('players') : '–' }}</div></div>
    </div>
    <p v-if="!live.stats.length" class="card p-8 text-center text-slate-500">
      {{ server.state === 'running' ? 'Collecting data…' : 'Start the server to see live metrics. The last 30 minutes are kept in memory.' }}
    </p>
    <div v-else class="grid gap-4 lg:grid-cols-2">
      <div class="card p-4"><h3 class="mb-2 text-sm font-semibold text-slate-300">CPU</h3><LineChart :labels="labels" :values="live.stats.map((p) => p.cpu)" :format="(v) => `${v}%`" :max="100" color="#f97316" /></div>
      <div class="card p-4"><h3 class="mb-2 text-sm font-semibold text-slate-300">Memory</h3><LineChart :labels="labels" :values="live.stats.map((p) => p.mem)" :format="bytes" color="#38bdf8" /></div>
      <div class="card p-4 lg:col-span-2"><h3 class="mb-2 text-sm font-semibold text-slate-300">Players</h3><LineChart :labels="labels" :values="live.stats.map((p) => p.players)" :max="server.max_players" color="#34d399" /></div>
    </div>
  </div>
</template>
