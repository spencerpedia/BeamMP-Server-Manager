<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { api, upload } from '../../api'
import { toast, toastError } from '../../store'
import { refreshServers } from '../../servers'
import { bytes, plural } from '../../format'
import { confirmDialog } from '../../components/confirm'
import Icon from '../../components/Icon.vue'
import Toggle from '../../components/Toggle.vue'
import UploadZone from '../../components/UploadZone.vue'
import ModBrowser from '../../components/ModBrowser.vue'
import { watchJob } from '../../jobs'

const server = inject('server')
const mods = ref([])
const browsing = ref(false)
const updates = ref({}) // filename -> latest version, when newer
const checking = ref(false)
const installedIds = computed(() => Object.fromEntries(mods.value.filter((m) => m.source).map((m) => [m.source.id, m.source.version])))

async function checkUpdates() {
  checking.value = true
  try {
    const results = await api.post(`${base.value}/mods/check-updates`)
    updates.value = Object.fromEntries(results.filter((r) => r.update).map((r) => [r.name, r.latest]))
    const n = Object.keys(updates.value).length
    toast(n ? `${n} update(s) available` : results.length ? 'All BeamNG.com mods are up to date' : 'No mods installed from BeamNG.com', n ? 'info' : 'success')
  } catch (e) {
    toastError(e)
  } finally {
    checking.value = false
  }
}

async function updateMod(m) {
  try {
    const job = await api.post(`${base.value}/mods/install`, { resource: String(m.source.id) })
    watchJob(job, {
      onDone: () => {
        delete updates.value[m.name]
        load()
      },
    })
  } catch (e) {
    toastError(e)
  }
}
const currentMap = ref('')
const progress = ref(null)
const filter = ref('')
const base = computed(() => `/api/servers/${server.value.id}`)
const shown = computed(() => mods.value.filter((m) => m.name.toLowerCase().includes(filter.value.toLowerCase())))
const totalSize = computed(() => mods.value.filter((m) => m.enabled).reduce((n, m) => n + m.size, 0))

async function load() {
  mods.value = await api.get(`${base.value}/mods`)
  currentMap.value = (await api.get(`${base.value}/maps`)).current
}
onMounted(() => load().catch(toastError))

async function onFiles(files) {
  const fd = new FormData()
  files.forEach((f) => fd.append('files', f))
  progress.value = 0
  try {
    const r = await upload(`${base.value}/mods`, fd, (p) => (progress.value = p))
    const maps = r.saved.flatMap((m) => m.maps)
    toast(`Uploaded ${r.saved.length} file(s)${maps.length ? `, found map ${maps.join(', ')}` : ''}`, 'success')
    await load()
  } catch (e) {
    toastError(e)
  } finally {
    progress.value = null
  }
}

async function toggle(m) {
  try {
    await api.patch(`${base.value}/mods/${encodeURIComponent(m.name)}`, { enabled: !m.enabled })
    await load()
  } catch (e) {
    toastError(e)
  }
}

async function remove(m) {
  if (!(await confirmDialog(`Delete ${m.name}?`, { danger: true, confirmText: 'Delete' }))) return
  try {
    await api.del(`${base.value}/mods/${encodeURIComponent(m.name)}`)
    await load()
  } catch (e) {
    toastError(e)
  }
}

async function useMap(level) {
  try {
    const r = await api.put(`${base.value}/maps`, { path: `/levels/${level}/info.json` })
    toast(r.restart_required ? `Map set to ${level}. Restart to apply.` : `Map set to ${level}`, 'success')
    await load()
    refreshServers()
  } catch (e) {
    toastError(e)
  }
}
</script>

<template>
  <div class="space-y-4">
    <UploadZone v-if="server.can_control" accept=".zip" multiple :progress="progress" :disabled="progress != null" hint="Vehicle and map mods as .zip files. They go to Resources/Client and are downloaded by players when they join." @files="onFiles" />

    <div class="card">
      <div class="flex flex-wrap items-center gap-3 border-b border-surface-700 px-5 py-3">
        <h2 class="font-semibold">Client mods</h2>
        <span class="text-xs text-slate-500">{{ plural(mods.length, 'file') }} · {{ bytes(totalSize) }} sent to players</span>
        <span class="flex-1" />
        <input v-model="filter" class="input max-w-xs py-1.5" placeholder="Filter…" />
        <button class="btn-ghost" :disabled="checking" @click="checkUpdates"><Icon name="refresh" :size="14" />{{ checking ? 'Checking…' : 'Check updates' }}</button>
        <button v-if="server.can_control" class="btn-primary" @click="browsing = true"><Icon name="package" :size="14" />Browse BeamNG.com</button>
      </div>
      <div class="overflow-x-auto">
        <table class="table">
          <thead>
            <tr><th>Name</th><th>Maps</th><th>Size</th><th>Enabled</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="m in shown" :key="m.name" :class="{ 'opacity-60': !m.enabled }">
              <td class="font-medium text-slate-200">
                <span class="flex items-center gap-2"><Icon name="package" class="shrink-0 text-slate-500" />
                  <span class="min-w-0">
                    <a v-if="m.source" :href="m.source.url" target="_blank" rel="noopener" class="block hover:text-accent-400">{{ m.source.title }} <span class="text-xs font-normal text-slate-500">v{{ m.source.version }}</span></a>
                    <span :class="m.source ? 'block text-xs font-normal text-slate-500' : ''">{{ m.name }}</span>
                  </span>
                  <button v-if="updates[m.name] && server.can_control" class="chip shrink-0 bg-sky-500/15 text-sky-300 hover:bg-sky-500/25" @click="updateMod(m)">Update to {{ updates[m.name] }}</button>
                </span>
              </td>
              <td>
                <div class="flex flex-wrap gap-1">
                  <template v-for="level in m.maps" :key="level">
                    <span v-if="currentMap.includes(`/levels/${level}/`)" class="chip bg-accent-500/15 text-accent-400"><Icon name="check" :size="12" />{{ level }} (active)</span>
                    <button v-else-if="server.can_control && m.enabled" class="chip bg-surface-700 text-slate-300 hover:bg-surface-600" @click="useMap(level)" title="Make this the server map"><Icon name="map" :size="12" />&nbsp;Use {{ level }}</button>
                    <span v-else class="chip bg-surface-700 text-slate-400">{{ level }}</span>
                  </template>
                  <span v-if="!m.maps.length" class="text-slate-600">—</span>
                </div>
              </td>
              <td class="whitespace-nowrap text-slate-400">{{ bytes(m.size) }}</td>
              <td><Toggle :model-value="m.enabled" :disabled="!server.can_control" @update:model-value="toggle(m)" /></td>
              <td class="text-right">
                <button v-if="server.can_control" class="text-slate-500 hover:text-red-400" title="Delete" @click="remove(m)"><Icon name="trash" /></button>
              </td>
            </tr>
            <tr v-if="!shown.length"><td colspan="5" class="py-8 text-center text-slate-500">No mods uploaded</td></tr>
          </tbody>
        </table>
      </div>
    </div>
    <ModBrowser v-if="browsing" :server-id="server.id" :installed="installedIds" @close="browsing = false" @installed="load" />
  </div>
</template>
