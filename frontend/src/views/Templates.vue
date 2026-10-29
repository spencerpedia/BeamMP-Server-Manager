<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, upload } from '../api'
import { toast, toastError } from '../store'
import { bytes, dateTime, plural } from '../format'
import { refreshServers } from '../servers'
import { confirmDialog } from '../components/confirm'
import Icon from '../components/Icon.vue'
import Modal from '../components/Modal.vue'
import SaveTemplate from '../components/SaveTemplate.vue'
import CreateServer from '../components/CreateServer.vue'

const router = useRouter()
const items = ref([])
const saving = ref(false)
const editing = ref(null)
const creatingFrom = ref(null)
const importInput = ref(null)
const importing = ref(null)

const load = async () => (items.value = await api.get('/api/templates'))
onMounted(() => load().catch(toastError))

async function rename() {
  try {
    await api.patch(`/api/templates/${editing.value.id}`, { name: editing.value.name, description: editing.value.description })
    editing.value = null
    await load()
  } catch (e) {
    toastError(e)
  }
}

async function remove(t) {
  if (!(await confirmDialog(`Delete template "${t.name}"? Servers created from it are not affected.`, { danger: true, confirmText: 'Delete' }))) return
  await api.del(`/api/templates/${t.id}`).catch(toastError)
  await load()
}

async function importFile(e) {
  const file = e.target.files[0]
  e.target.value = ''
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  importing.value = 0
  try {
    const t = await upload('/api/templates/import', fd, (p) => (importing.value = p))
    toast(`Imported template ${t.name}`, 'success')
    await load()
  } catch (err) {
    toastError(err)
  } finally {
    importing.value = null
  }
}

function created(s) {
  creatingFrom.value = null
  refreshServers()
  router.push(`/servers/${s.id}/console`)
}
</script>

<template>
  <div class="mx-auto max-w-6xl p-4 md:p-8">
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">Templates</h1>
        <p class="text-sm text-slate-400">Saved setups (config, mods and plugins) to spin up new servers from</p>
      </div>
      <div class="flex gap-2">
        <button class="btn-ghost" :disabled="importing != null" @click="importInput.click()">
          <Icon name="upload" :size="14" />{{ importing != null ? `Uploading ${Math.round(importing * 100)}%` : 'Import .zip' }}
        </button>
        <input ref="importInput" type="file" accept=".zip" class="hidden" @change="importFile" />
        <button class="btn-primary" @click="saving = true"><Icon name="plus" />Save server as template</button>
      </div>
    </div>

    <div v-if="!items.length" class="card p-12 text-center text-slate-500">
      No templates yet. Save one from any server, or import a template someone shared with you.
    </div>
    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <div v-for="t in items" :key="t.id" class="card flex flex-col p-5">
        <div class="flex items-start justify-between gap-2">
          <h3 class="text-lg font-semibold text-slate-100">{{ t.name }}</h3>
          <span v-if="t.includes_auth_key" class="chip bg-amber-500/15 text-amber-300" title="Contains an auth key">key</span>
        </div>
        <p class="mt-1 flex-1 text-sm text-slate-400">{{ t.description || (t.source ? `From ${t.source}` : '') }}</p>
        <div class="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div class="rounded-lg bg-surface-800 py-2"><div class="font-semibold text-slate-200">{{ t.mods }}</div>{{ plural(t.mods, 'mod').split(' ')[1] }}</div>
          <div class="rounded-lg bg-surface-800 py-2"><div class="font-semibold text-slate-200">{{ t.plugins }}</div>{{ plural(t.plugins, 'plugin').split(' ')[1] }}</div>
          <div class="rounded-lg bg-surface-800 py-2"><div class="font-semibold text-slate-200">{{ bytes(t.size) }}</div>size</div>
        </div>
        <p class="mt-3 text-xs text-slate-500">{{ (t.map || '').split('/')[2] || '—' }} · {{ t.max_players }} players · {{ dateTime(t.created) }}</p>
        <div class="mt-4 flex gap-2 border-t border-surface-700 pt-3">
          <button class="btn-primary flex-1" @click="creatingFrom = t.id"><Icon name="plus" :size="14" />New server</button>
          <a class="btn-ghost" :href="`/api/templates/${t.id}/export`" title="Export as .zip"><Icon name="download" :size="14" /></a>
          <button class="btn-ghost" title="Rename" @click="editing = { ...t }"><Icon name="edit" :size="14" /></button>
          <button class="btn-ghost text-red-300" title="Delete" @click="remove(t)"><Icon name="trash" :size="14" /></button>
        </div>
      </div>
    </div>

    <SaveTemplate v-if="saving" @close="saving = false" @saved="load" />
    <CreateServer v-if="creatingFrom" :initial-template="creatingFrom" @close="creatingFrom = null" @created="created" />
    <Modal v-if="editing" title="Edit template" @close="editing = null">
      <form id="tpl-edit" class="space-y-4" @submit.prevent="rename">
        <div><label class="label">Name</label><input v-model="editing.name" class="input" required /></div>
        <div><label class="label">Description</label><textarea v-model="editing.description" rows="3" class="input" /></div>
      </form>
      <template #footer>
        <button class="btn-ghost" @click="editing = null">Cancel</button>
        <button class="btn-primary" form="tpl-edit">Save</button>
      </template>
    </Modal>
  </div>
</template>
