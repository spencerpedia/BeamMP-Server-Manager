<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { toast, toastError } from '../store'
import { bytes, dateTime } from '../format'
import { confirmDialog } from '../components/confirm'
import Icon from '../components/Icon.vue'

const data = ref(null)
const busy = ref('')

async function load(refresh = false) {
  data.value = await api.get(`/api/versions${refresh ? '?refresh=true' : ''}`)
}
onMounted(() => load().catch(toastError))

const isInstalled = (tag) => data.value?.installed.some((i) => i.tag === tag)

async function install(tag) {
  busy.value = tag
  try {
    await api.post(`/api/versions/${tag}`)
    toast(`Downloaded ${tag}`, 'success')
    await load()
  } catch (e) {
    toastError(e)
  } finally {
    busy.value = ''
  }
}

async function remove(tag) {
  if (!(await confirmDialog(`Delete the downloaded ${tag} binary?`, { danger: true, confirmText: 'Delete' }))) return
  try {
    await api.del(`/api/versions/${tag}`)
    await load()
  } catch (e) {
    toastError(e)
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl p-4 md:p-8">
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">BeamMP-Server versions</h1>
        <p class="text-sm text-slate-400">Release binaries from GitHub ({{ data?.asset }}). Servers on "latest" pick up new versions when they restart.</p>
      </div>
      <button class="btn-ghost" @click="load(true)"><Icon name="refresh" />Check for updates</button>
    </div>
    <p v-if="data?.error" class="mb-4 rounded-lg bg-amber-500/10 px-4 py-2 text-sm text-amber-300">Couldn't reach GitHub: {{ data.error }}</p>
    <div class="card overflow-x-auto">
      <table class="table">
        <thead><tr><th>Version</th><th>Released</th><th>Size</th><th>Status</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in data?.available || []" :key="r.tag">
            <td class="font-medium">
              <a :href="r.notes_url" target="_blank" rel="noopener" class="hover:text-accent-400">{{ r.tag }}</a>
              <span v-if="r.tag === data.latest" class="chip ml-2 bg-accent-500/15 text-accent-400">latest</span>
            </td>
            <td class="text-slate-400">{{ dateTime(r.published_at) }}</td>
            <td class="text-slate-400">{{ bytes(r.size) }}</td>
            <td>
              <span v-if="isInstalled(r.tag)" class="chip bg-emerald-500/15 text-emerald-300">downloaded</span>
              <span v-if="data.installed.find((i) => i.tag === r.tag)?.in_use" class="chip ml-1 bg-sky-500/15 text-sky-300">running</span>
            </td>
            <td class="text-right">
              <button v-if="!isInstalled(r.tag)" class="btn-ghost py-1 text-xs" :disabled="!!busy" @click="install(r.tag)">
                <Icon name="download" :size="12" />{{ busy === r.tag ? 'Downloading…' : 'Download' }}
              </button>
              <button v-else class="btn-ghost py-1 text-xs text-red-300" @click="remove(r.tag)"><Icon name="trash" :size="12" /></button>
            </td>
          </tr>
          <tr v-if="data && !data.available.length">
            <td colspan="5" class="py-6 text-center text-slate-500">Installed: {{ data.installed.map((i) => i.tag).join(', ') || 'none' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
