<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { isAdmin, toast, toastError } from '../store'
import { servers, refreshServers } from '../servers'
import { bytes, duration, plainName } from '../format'
import Icon from '../components/Icon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import CreateServer from '../components/CreateServer.vue'

const router = useRouter()
const creating = ref(false)
const busy = ref({})

const totals = computed(() => {
  const running = servers.list.filter((s) => s.state === 'running')
  return {
    servers: servers.list.length,
    running: running.length,
    players: running.reduce((n, s) => n + (s.players?.length || 0), 0),
    mem: running.reduce((n, s) => n + (s.stats?.mem || 0), 0),
  }
})

async function act(s, action) {
  busy.value[s.id] = true
  try {
    await api.post(`/api/servers/${s.id}/${action}`)
    await refreshServers()
  } catch (e) {
    toastError(e)
  } finally {
    busy.value[s.id] = false
  }
}

function created(s) {
  creating.value = false
  toast(`Created ${s.name}`, 'success')
  refreshServers()
  router.push(`/servers/${s.id}/config`)
}
</script>

<template>
  <div class="mx-auto max-w-7xl p-4 md:p-8">
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold text-slate-100">Dashboard</h1>
        <p class="text-sm text-slate-400">All your BeamMP servers at a glance</p>
      </div>
      <button v-if="isAdmin()" class="btn-primary" @click="creating = true"><Icon name="plus" />New server</button>
    </div>

    <div class="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
      <div class="card p-4">
        <div class="text-xs uppercase tracking-wide text-slate-400">Servers</div>
        <div class="mt-1 text-2xl font-bold">{{ totals.servers }}</div>
      </div>
      <div class="card p-4">
        <div class="text-xs uppercase tracking-wide text-slate-400">Running</div>
        <div class="mt-1 text-2xl font-bold text-emerald-400">{{ totals.running }}</div>
      </div>
      <div class="card p-4">
        <div class="text-xs uppercase tracking-wide text-slate-400">Players online</div>
        <div class="mt-1 text-2xl font-bold text-accent-400">{{ totals.players }}</div>
      </div>
      <div class="card p-4">
        <div class="text-xs uppercase tracking-wide text-slate-400">Memory in use</div>
        <div class="mt-1 text-2xl font-bold">{{ bytes(totals.mem) }}</div>
      </div>
    </div>

    <div v-if="servers.loaded && !servers.list.length" class="card flex flex-col items-center p-12 text-center">
      <Icon name="server" :size="40" class="mb-3 text-slate-500" />
      <h2 class="text-lg font-semibold">No servers yet</h2>
      <p class="mb-4 mt-1 max-w-md text-sm text-slate-400">
        Create your first BeamMP server. You'll need an Auth Key from
        <a href="https://keymaster.beammp.com" target="_blank" rel="noopener" class="text-accent-400 hover:underline">keymaster.beammp.com</a>.
      </p>
      <button v-if="isAdmin()" class="btn-primary" @click="creating = true"><Icon name="plus" />New server</button>
      <p v-else class="text-sm text-slate-500">Ask an admin to give you access to a server.</p>
    </div>

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <div v-for="s in servers.list" :key="s.id" class="card flex flex-col transition hover:border-surface-600">
        <RouterLink :to="`/servers/${s.id}`" class="block p-5">
          <div class="mb-3 flex items-start justify-between gap-3">
            <div class="min-w-0">
              <h3 class="truncate text-lg font-semibold text-slate-100">{{ plainName(s.name) }}</h3>
              <p class="text-xs text-slate-400">Port {{ s.port }} · {{ s.map || '—' }}</p>
            </div>
            <StatusBadge :state="s.state" />
          </div>
          <div class="grid grid-cols-3 gap-2 text-sm">
            <div class="rounded-lg bg-surface-800 px-3 py-2">
              <div class="text-xs text-slate-400">Players</div>
              <div class="font-semibold">{{ s.state === 'running' ? s.players?.length || 0 : '–' }}<span class="text-slate-500">/{{ s.max_players }}</span></div>
            </div>
            <div class="rounded-lg bg-surface-800 px-3 py-2">
              <div class="text-xs text-slate-400">CPU</div>
              <div class="font-semibold">{{ s.stats ? `${s.stats.cpu}%` : '–' }}</div>
            </div>
            <div class="rounded-lg bg-surface-800 px-3 py-2">
              <div class="text-xs text-slate-400">RAM</div>
              <div class="font-semibold">{{ s.stats ? bytes(s.stats.mem) : '–' }}</div>
            </div>
          </div>
          <p v-if="!s.has_auth_key" class="mt-3 rounded-lg bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300">No Auth Key set. Add one in Config.</p>
        </RouterLink>
        <div class="mt-auto flex items-center gap-2 border-t border-surface-700 px-5 py-3">
          <span class="flex-1 text-xs text-slate-500">{{ s.state === 'running' ? `Up ${duration(s.uptime)} · ${s.version_running || s.version}` : s.version === 'latest' ? 'Latest version' : s.version }}</span>
          <template v-if="s.can_control">
            <button v-if="['stopped', 'crashed'].includes(s.state)" class="btn-success" :disabled="busy[s.id] || s.provisioning" @click="act(s, 'start')"><Icon name="play" :size="14" />Start</button>
            <template v-else>
              <button class="btn-ghost" :disabled="busy[s.id] || s.state !== 'running'" @click="act(s, 'restart')" title="Restart"><Icon name="restart" :size="14" /></button>
              <button class="btn-danger" :disabled="busy[s.id] || s.state === 'stopping'" @click="act(s, 'stop')"><Icon name="stop" :size="14" />Stop</button>
            </template>
          </template>
        </div>
      </div>
    </div>

    <CreateServer v-if="creating" @close="creating = false" @created="created" />
  </div>
</template>
