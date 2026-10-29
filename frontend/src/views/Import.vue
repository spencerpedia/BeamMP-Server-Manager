<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { toastError } from '../store'
import { refreshServers } from '../servers'
import { watchJob } from '../jobs'
import { bytes } from '../format'
import Icon from '../components/Icon.vue'
import Modal from '../components/Modal.vue'

const router = useRouter()
const scan = ref(null)
const loading = ref(false)
const target = ref(null)
const system = ref(null)

async function load() {
  loading.value = true
  try {
    scan.value = await api.get('/api/import/scan')
  } catch (e) {
    toastError(e)
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  system.value = await api.get('/api/system')
  load()
})

function choose(s) {
  target.value = { path: s.path, name: s.name, port: null, original_port: s.port, size: s.size }
}

async function doImport() {
  try {
    const r = await api.post('/api/import', { path: target.value.path, name: target.value.name, port: target.value.port || null })
    watchJob(r.job, { onDone: () => refreshServers() })
    target.value = null
    await refreshServers()
    router.push(`/servers/${r.id}/mods`)
  } catch (e) {
    toastError(e)
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl p-4 md:p-8">
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">Import servers</h1>
        <p class="text-sm text-slate-400">Bring existing BeamMP server folders under the panel. The originals are only read, never changed.</p>
      </div>
      <button class="btn-ghost" :disabled="loading" @click="load"><Icon name="refresh" :size="14" />Rescan</button>
    </div>

    <div v-if="scan && !scan.mounted" class="card p-6 text-sm text-slate-300">
      <h2 class="mb-2 font-semibold text-slate-100">No import folder mounted</h2>
      <p>
        Add a read-only path mapping to the container with container path <code class="text-accent-400">{{ scan.path }}</code>, pointing at the folder that holds
        your old server, for example <code class="text-accent-400">/mnt/user/appdata</code> or <code class="text-accent-400">/mnt/cache/appdata/beamng-mp</code>.
      </p>
      <p class="mt-2 text-slate-400">In Unraid: Docker → edit this container → "Import (read-only)" path → Apply. Then come back and click Rescan.</p>
    </div>

    <div v-else-if="scan" class="card overflow-x-auto">
      <table class="table">
        <thead><tr><th>Folder</th><th>Server</th><th>Mods</th><th>Plugins</th><th>Size</th><th></th></tr></thead>
        <tbody>
          <tr v-for="s in scan.servers" :key="s.path">
            <td class="font-mono text-xs text-slate-300">{{ scan.path }}/{{ s.path === '.' ? '' : s.path }}</td>
            <td>
              <div class="font-medium text-slate-100">{{ s.name }}</div>
              <div class="text-xs text-slate-500">{{ (s.map || '').split('/')[2] }} · port {{ s.port }} · {{ s.has_auth_key ? 'has auth key' : 'no auth key' }}</div>
            </td>
            <td>{{ s.mods }}<span v-if="s.mods_disabled" class="text-xs text-slate-500"> (+{{ s.mods_disabled }} off)</span></td>
            <td>{{ s.plugins }}</td>
            <td class="whitespace-nowrap text-slate-400">{{ bytes(s.size) }}</td>
            <td class="text-right"><button class="btn-primary py-1 text-xs" @click="choose(s)">Import</button></td>
          </tr>
          <tr v-if="!scan.servers.length"><td colspan="6" class="py-8 text-center text-slate-500">No ServerConfig.toml found under {{ scan.path }} (searched 4 levels deep)</td></tr>
        </tbody>
      </table>
    </div>

    <Modal v-if="target" title="Import server" @close="target = null">
      <form id="imp" class="space-y-4" @submit.prevent="doImport">
        <div><label class="label">Name</label><input v-model="target.name" class="input" required /></div>
        <div>
          <label class="label">Port</label>
          <input v-model.number="target.port" type="number" class="input" :placeholder="`Auto (keeps ${target.original_port} if free)`" />
          <p class="help">
            Must be inside {{ system?.port_range.join('–') }}. If the old server still runs on {{ target.original_port }}, stop it or pick another port.
          </p>
        </div>
        <p class="text-xs text-slate-500">Copies {{ bytes(target.size) }} of mods and plugins plus all config values (including the auth key). This runs in the background.</p>
      </form>
      <template #footer>
        <button class="btn-ghost" @click="target = null">Cancel</button>
        <button class="btn-primary" form="imp">Import</button>
      </template>
    </Modal>
  </div>
</template>
