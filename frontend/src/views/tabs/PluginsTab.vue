<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { api, upload } from '../../api'
import { toast, toastError } from '../../store'
import { bytes } from '../../format'
import { confirmDialog } from '../../components/confirm'
import Icon from '../../components/Icon.vue'
import Toggle from '../../components/Toggle.vue'
import UploadZone from '../../components/UploadZone.vue'
import PluginBrowser from '../../components/PluginBrowser.vue'

const server = inject('server')
const plugins = ref([])
const browsing = ref(false)
const progress = ref(null)
const base = computed(() => `/api/servers/${server.value.id}`)

const load = async () => (plugins.value = await api.get(`${base.value}/plugins`))
onMounted(() => load().catch(toastError))

async function onFiles([file]) {
  const fd = new FormData()
  fd.append('file', file)
  progress.value = 0
  try {
    const r = await upload(`${base.value}/plugins`, fd, (p) => (progress.value = p))
    toast(`Installed plugin ${r.name}. BeamMP hot-reloads Lua plugins, or restart to be sure.`, 'success')
    await load()
  } catch (e) {
    toastError(e)
  } finally {
    progress.value = null
  }
}

async function toggle(p) {
  try {
    await api.patch(`${base.value}/plugins/${encodeURIComponent(p.name)}`, { enabled: !p.enabled })
    toast(server.value.state === 'running' ? 'Restart the server to apply' : 'Saved')
    await load()
  } catch (e) {
    toastError(e)
  }
}

async function remove(p) {
  if (!(await confirmDialog(`Delete plugin ${p.name} and all its files?`, { danger: true, confirmText: 'Delete' }))) return
  try {
    await api.del(`${base.value}/plugins/${encodeURIComponent(p.name)}`)
    await load()
  } catch (e) {
    toastError(e)
  }
}
</script>

<template>
  <div class="space-y-4">
    <UploadZone v-if="server.can_control" accept=".zip,.lua" :progress="progress" :disabled="progress != null" hint="A .zip of a plugin folder, or a single .lua file. Installed to Resources/Server/<name>." @files="onFiles" />
    <div class="card">
      <div class="flex items-center justify-between border-b border-surface-700 px-5 py-3">
        <h2 class="font-semibold">Server plugins (Lua)</h2>
        <button v-if="server.can_control" class="btn-primary" @click="browsing = true"><Icon name="code" :size="14" />Browse plugins</button>
      </div>
      <table class="table">
        <thead><tr><th>Name</th><th>Files</th><th>Size</th><th>Enabled</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in plugins" :key="p.name" :class="{ 'opacity-60': !p.enabled }">
            <td class="font-medium text-slate-200"><span class="flex items-center gap-2"><Icon name="code" class="text-slate-500" />{{ p.name }}</span></td>
            <td class="text-slate-400">{{ p.files }}</td>
            <td class="text-slate-400">{{ bytes(p.size) }}</td>
            <td><Toggle :model-value="p.enabled" :disabled="!server.can_control" @update:model-value="toggle(p)" /></td>
            <td class="text-right"><button v-if="server.can_control" class="text-slate-500 hover:text-red-400" title="Delete" @click="remove(p)"><Icon name="trash" /></button></td>
          </tr>
          <tr v-if="!plugins.length"><td colspan="5" class="py-8 text-center text-slate-500">No plugins installed</td></tr>
        </tbody>
      </table>
      <p class="border-t border-surface-700 px-5 py-3 text-xs text-slate-500">
        The panel also installs a small hidden bridge plugin (_BMSM) into every server for player tracking, chat logging and bans.
      </p>
    </div>
    <PluginBrowser v-if="browsing" :server-id="server.id" @close="browsing = false" @installed="load" />
  </div>
</template>
