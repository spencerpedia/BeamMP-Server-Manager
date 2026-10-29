<script setup>
import { computed, onBeforeUnmount, provide, reactive, ref, watch } from 'vue'
import { api, socket } from '../api'
import { toastError } from '../store'
import { findServer, refreshServers, servers } from '../servers'
import { duration, plainName } from '../format'
import { confirmDialog } from '../components/confirm'
import Icon from '../components/Icon.vue'
import StatusBadge from '../components/StatusBadge.vue'

const props = defineProps({ id: Number })
const server = computed(() => findServer(props.id))
const busy = ref(false)

// Live per-server feed shared with the tabs.
const live = reactive({ log: [], players: [], chat: [], stats: [], state: null, connected: false })
const logListeners = new Set()
provide('server', server)
provide('live', live)
provide('onLog', (fn) => {
  logListeners.add(fn)
  return () => logListeners.delete(fn)
})

let close = null
function connect(id) {
  close?.()
  Object.assign(live, { log: [], players: [], chat: [], stats: [], state: null })
  api.get(`/api/servers/${id}/stats`).then((r) => (live.stats = r.points)).catch(() => {})
  api.get(`/api/servers/${id}/chat`).then((r) => (live.chat = r)).catch(() => {})
  close = socket(
    `/ws/servers/${id}`,
    (msg) => {
      switch (msg.type) {
        case 'hello':
          live.log = msg.log
          live.players = msg.players
          live.state = msg.state
          logListeners.forEach((fn) => fn(null, msg.log))
          break
        case 'log':
          live.log.push(msg.line)
          if (live.log.length > 3000) live.log.splice(0, live.log.length - 3000)
          logListeners.forEach((fn) => fn(msg.line))
          break
        case 'players':
          live.players = msg.players
          break
        case 'chat':
          live.chat.push(msg)
          break
        case 'stats':
          live.stats.push(msg)
          if (live.stats.length > 900) live.stats.shift()
          break
        case 'state':
          live.state = msg.state
          break
      }
    },
    (ok) => (live.connected = ok),
  )
}
watch(() => props.id, connect, { immediate: true })
onBeforeUnmount(() => close?.())

watch(
  () => servers.loaded,
  (loaded) => loaded || refreshServers().catch(() => {}),
  { immediate: true },
)

const state = computed(() => server.value?.state || live.state || 'stopped')

async function act(action) {
  if (action === 'kill' && !(await confirmDialog('Force-kill the server process? Players are dropped without a clean shutdown.', { danger: true, confirmText: 'Kill' })))
    return
  busy.value = true
  try {
    await api.post(`/api/servers/${props.id}/${action}`)
    await refreshServers()
  } catch (e) {
    toastError(e)
  } finally {
    busy.value = false
  }
}

const tabs = [
  ['console', 'Console', 'terminal'],
  ['config', 'Config', 'sliders'],
  ['mods', 'Mods & Maps', 'map'],
  ['plugins', 'Plugins', 'code'],
  ['players', 'Players', 'users'],
  ['metrics', 'Metrics', 'chart'],
  ['schedules', 'Schedules', 'clock'],
  ['backups', 'Backups', 'archive'],
  ['settings', 'Settings', 'settings'],
]
</script>

<template>
  <div v-if="server" class="mx-auto flex max-w-7xl flex-col p-4 md:p-8">
    <div class="mb-5 flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0">
        <div class="flex items-center gap-3">
          <h1 class="truncate text-2xl font-bold text-slate-100">{{ plainName(server.name) }}</h1>
          <StatusBadge :state="state" />
        </div>
        <p class="mt-1 text-sm text-slate-400">
          Port {{ server.port }} · {{ server.map }} ·
          <template v-if="state === 'running'">{{ live.players.length }}/{{ server.max_players }} players · up {{ duration(server.uptime) }} · v{{ (server.version_running || server.version).replace(/^v/, '') }}</template>
          <template v-else>{{ server.version === 'latest' ? 'latest version' : server.version }}</template>
        </p>
      </div>
      <div v-if="server.can_control" class="flex gap-2">
        <span v-if="server.provisioning" class="chip self-center bg-sky-500/15 text-sky-300">Copying files…</span>
        <button v-if="['stopped', 'crashed'].includes(state)" class="btn-success" :disabled="busy || server.provisioning" @click="act('start')"><Icon name="play" :size="14" />Start</button>
        <template v-else>
          <button class="btn-ghost" :disabled="busy || state !== 'running'" @click="act('restart')"><Icon name="restart" :size="14" />Restart</button>
          <button class="btn-danger" :disabled="busy || state === 'stopping'" @click="act('stop')"><Icon name="stop" :size="14" />Stop</button>
          <button class="btn-ghost text-red-300" :disabled="busy" title="Force kill" @click="act('kill')"><Icon name="kill" :size="14" /></button>
        </template>
      </div>
    </div>

    <nav class="mb-5 flex gap-1 overflow-x-auto border-b border-surface-700 text-sm">
      <RouterLink
        v-for="[path, label, icon] in tabs"
        :key="path"
        :to="`/servers/${id}/${path}`"
        class="-mb-px flex shrink-0 items-center gap-1.5 border-b-2 border-transparent px-3 py-2.5 text-slate-400 transition hover:text-slate-100"
        active-class="!border-accent-500 !text-accent-400"
      >
        <Icon :name="icon" :size="15" />{{ label }}
      </RouterLink>
    </nav>

    <RouterView :key="id" />
  </div>
  <div v-else-if="servers.loaded" class="p-8 text-slate-400">Server not found, or you don't have access to it.</div>
</template>
