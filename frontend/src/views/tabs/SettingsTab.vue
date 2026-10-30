<script setup>
import { inject, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import { isAdmin, toast, toastError } from '../../store'
import { refreshServers } from '../../servers'
import { confirmDialog } from '../../components/confirm'
import Toggle from '../../components/Toggle.vue'
import Icon from '../../components/Icon.vue'
import SaveTemplate from '../../components/SaveTemplate.vue'
import CreateServer from '../../components/CreateServer.vue'

const server = inject('server')
const router = useRouter()
const savingTemplate = ref(false)
const cloning = ref(false)

function cloned(s) {
  cloning.value = false
  refreshServers()
  router.push(`/servers/${s.id}/console`)
}
const form = ref({})
const versions = ref([])
const system = ref(null)
const deleteBackups = ref(false)

const EVENT_LABELS = { status: 'Server status', players: 'Player join/leave', tasks: 'Schedules & backups' }
const discord = ref(null)
const showWebhook = ref(false)
const testing = ref(false)

onMounted(async () => {
  const s = server.value
  form.value = { name: s.name, port: s.port, version: s.version, autostart: s.autostart, auto_restart: s.auto_restart, backup_retention: s.backup_retention }
  system.value = await api.get('/api/system')
  if (s.can_control) api.get(`/api/servers/${s.id}/discord`).then((d) => (discord.value = d)).catch(toastError)
  try {
    const v = await api.get('/api/versions')
    versions.value = [...new Set([...v.installed.map((i) => i.tag), ...v.available.map((a) => a.tag)])]
  } catch {}
})

async function save() {
  try {
    await api.patch(`/api/servers/${server.value.id}`, form.value)
    await refreshServers()
    toast(server.value.state === 'running' ? 'Saved. Version changes apply on the next restart.' : 'Saved', 'success')
  } catch (e) {
    toastError(e)
  }
}

async function saveDiscord() {
  try {
    discord.value = await api.put(`/api/servers/${server.value.id}/discord`, discord.value)
    toast('Saved', 'success')
  } catch (e) {
    toastError(e)
  }
}

async function testDiscord() {
  testing.value = true
  try {
    await api.post(`/api/servers/${server.value.id}/discord/test`, { webhook_url: discord.value.webhook_url })
    toast('Test message sent', 'success')
  } catch (e) {
    toastError(e)
  } finally {
    testing.value = false
  }
}

async function remove() {
  const ok = await confirmDialog(
    `Permanently delete "${server.value.name}"? The server is stopped, and its config, mods and plugins are deleted${deleteBackups.value ? ', along with all its backups' : ''}.`,
    { danger: true, confirmText: 'Delete server' },
  )
  if (!ok) return
  try {
    await api.del(`/api/servers/${server.value.id}?delete_backups=${deleteBackups.value}`)
    await refreshServers()
    toast('Server deleted', 'success')
    router.push('/')
  } catch (e) {
    toastError(e)
  }
}
</script>

<template>
  <div class="space-y-4">
    <form class="card grid gap-5 p-5 md:grid-cols-2" @submit.prevent="save">
      <div>
        <label class="label">Display name</label>
        <input v-model="form.name" class="input" required :disabled="!server.can_control" />
      </div>
      <div>
        <label class="label">Port (TCP + UDP)</label>
        <input v-model.number="form.port" type="number" class="input" :disabled="!server.can_control || server.state !== 'stopped'" />
        <p class="help">
          Must be inside {{ system?.port_range.join('–') }} and published by the container.
          <template v-if="server.state !== 'stopped'">Stop the server to change it.</template>
        </p>
      </div>
      <div>
        <label class="label">BeamMP-Server version</label>
        <select v-model="form.version" class="input" :disabled="!server.can_control">
          <option value="latest">Latest (updates on restart)</option>
          <option v-for="v in versions" :key="v" :value="v">{{ v }} (pinned)</option>
        </select>
      </div>
      <div>
        <label class="label">Backups to keep</label>
        <input v-model.number="form.backup_retention" type="number" min="0" class="input" :disabled="!server.can_control" />
        <p class="help">0 keeps every backup.</p>
      </div>
      <div class="flex items-center justify-between gap-4 rounded-lg bg-surface-800 px-4 py-3">
        <div>
          <div class="text-sm font-medium">Start with the panel</div>
          <div class="text-xs text-slate-500">Starts automatically when the container starts.</div>
        </div>
        <Toggle v-model="form.autostart" :disabled="!server.can_control" />
      </div>
      <div class="flex items-center justify-between gap-4 rounded-lg bg-surface-800 px-4 py-3">
        <div>
          <div class="text-sm font-medium">Restart on crash</div>
          <div class="text-xs text-slate-500">Up to 3 times in 5 minutes.</div>
        </div>
        <Toggle v-model="form.auto_restart" :disabled="!server.can_control" />
      </div>
      <div v-if="server.can_control" class="flex justify-end md:col-span-2">
        <button class="btn-primary">Save settings</button>
      </div>
    </form>

    <form v-if="server.can_control && discord" class="card space-y-4 p-5" @submit.prevent="saveDiscord">
      <div class="flex items-center justify-between gap-4">
        <div>
          <h3 class="font-semibold">Discord notifications</h3>
          <p class="text-sm text-slate-400">Post this server's events to a Discord channel. Off unless you add a webhook.</p>
        </div>
        <Toggle v-model="discord.enabled" />
      </div>
      <div>
        <label class="label">Webhook URL</label>
        <div class="flex gap-2">
          <input v-model="discord.webhook_url" :type="showWebhook ? 'text' : 'password'" class="input font-mono" autocomplete="off" placeholder="https://discord.com/api/webhooks/…" />
          <button type="button" class="btn-ghost" @click="showWebhook = !showWebhook" :title="showWebhook ? 'Hide' : 'Show'"><Icon :name="showWebhook ? 'eyeoff' : 'eye'" /></button>
        </div>
        <p class="help">In Discord: Edit channel → Integrations → Webhooks → New Webhook → Copy Webhook URL.</p>
      </div>
      <div class="flex flex-wrap gap-x-6 gap-y-2">
        <label v-for="(label, key) in EVENT_LABELS" :key="key" class="flex items-center gap-2 text-sm text-slate-300">
          <input v-model="discord.events" type="checkbox" :value="key" class="accent-orange-500" />{{ label }}
        </label>
      </div>
      <div class="flex justify-end gap-2">
        <button type="button" class="btn-ghost" :disabled="testing || !discord.webhook_url" @click="testDiscord"><Icon name="send" :size="14" />Send test message</button>
        <button class="btn-primary">Save</button>
      </div>
    </form>

    <div v-if="isAdmin()" class="card flex flex-wrap items-center gap-3 p-5">
      <div class="flex-1">
        <h3 class="font-semibold">Reuse this setup</h3>
        <p class="text-sm text-slate-400">Save the config, mods and plugins as a template, or create a copy of this server.</p>
      </div>
      <button class="btn-ghost" @click="savingTemplate = true"><Icon name="layers" :size="14" />Save as template</button>
      <button class="btn-ghost" @click="cloning = true"><Icon name="plus" :size="14" />Clone server</button>
    </div>
    <SaveTemplate v-if="savingTemplate" :server-id="server.id" @close="savingTemplate = false" />
    <CreateServer v-if="cloning" :initial-clone="server.id" @close="cloning = false" @created="cloned" />

    <div v-if="isAdmin()" class="card border-red-500/30 p-5">
      <h3 class="font-semibold text-red-300">Danger zone</h3>
      <p class="mb-3 mt-1 text-sm text-slate-400">Deleting a server removes its directory from /data. This can't be undone.</p>
      <label class="mb-3 flex items-center gap-2 text-sm text-slate-300"><input v-model="deleteBackups" type="checkbox" class="accent-red-500" />Also delete its backups</label>
      <button class="btn-danger" @click="remove">Delete server</button>
    </div>
  </div>
</template>
