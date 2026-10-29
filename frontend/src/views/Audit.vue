<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { toastError } from '../store'
import { servers } from '../servers'
import { dateTime, plainName } from '../format'

const rows = ref([])
const filter = ref('')
onMounted(async () => {
  try {
    rows.value = await api.get('/api/audit?limit=500')
  } catch (e) {
    toastError(e)
  }
})
const shown = computed(() => {
  const q = filter.value.toLowerCase()
  return q ? rows.value.filter((r) => `${r.username} ${r.action} ${r.detail}`.toLowerCase().includes(q)) : rows.value
})
const serverName = (id) => (id == null ? '' : plainName(servers.list.find((s) => s.id === id)?.name || `#${id}`))
</script>

<template>
  <div class="mx-auto max-w-6xl p-4 md:p-8">
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">Audit log</h1>
        <p class="text-sm text-slate-400">The last 500 actions taken in the panel</p>
      </div>
      <input v-model="filter" class="input max-w-xs" placeholder="Filter…" />
    </div>
    <div class="card overflow-x-auto">
      <table class="table">
        <thead><tr><th>When</th><th>User</th><th>Server</th><th>Action</th><th>Detail</th></tr></thead>
        <tbody>
          <tr v-for="r in shown" :key="r.id">
            <td class="whitespace-nowrap text-xs text-slate-500">{{ dateTime(r.ts) }}</td>
            <td class="font-medium">{{ r.username }}</td>
            <td class="text-slate-400">{{ serverName(r.server_id) }}</td>
            <td><code class="text-xs text-accent-400">{{ r.action }}</code></td>
            <td class="max-w-md truncate text-slate-400" :title="r.detail">{{ r.detail }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
