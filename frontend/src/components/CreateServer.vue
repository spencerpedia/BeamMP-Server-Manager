<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { toastError } from '../store'
import Modal from './Modal.vue'
import { servers, refreshServers } from '../servers'
import { watchJob } from '../jobs'
import { plainName } from '../format'

const emit = defineEmits(['close', 'created'])
const props = defineProps({ initialTemplate: String, initialClone: Number })
const form = ref({ name: '', auth_key: '', port: null, version: 'latest', max_players: 8, map: '/levels/gridmap_v2/info.json' })
const source = ref(props.initialTemplate ? 'template' : props.initialClone ? 'clone' : 'blank')
const templateId = ref(props.initialTemplate || '')
const cloneFrom = ref(props.initialClone || null)
const templateList = ref([])
const system = ref(null)
const versions = ref([])
const busy = ref(false)
const maps = [
  ['gridmap_v2', 'Grid Map V2'], ['west_coast_usa', 'West Coast, USA'], ['east_coast_usa', 'East Coast, USA'],
  ['utah', 'Utah, USA'], ['italy', 'Italy'], ['johnson_valley', 'Johnson Valley'], ['jungle_rock_island', 'Jungle Rock Island'],
  ['hirochi_raceway', 'Hirochi Raceway'], ['automation_test_track', 'Automation Test Track'], ['industrial', 'Industrial Site'],
  ['small_island', 'Small Island, USA'], ['derby', 'Derby Arenas'], ['driver_training', 'Driver Training'], ['smallgrid', 'Grid, Small, Pure'],
]

onMounted(async () => {
  system.value = await api.get('/api/system')
  api.get('/api/templates').then((t) => {
    templateList.value = t
    if (!templateId.value && t.length) templateId.value = t[0].id
  })
  if (!cloneFrom.value && servers.list.length) cloneFrom.value = servers.list[0].id
  try {
    const v = await api.get('/api/versions')
    versions.value = [...new Set([...v.installed.map((i) => i.tag), ...v.available.map((a) => a.tag)])]
  } catch {}
})

async function submit() {
  busy.value = true
  try {
    const body = { ...form.value, port: form.value.port || null }
    if (source.value === 'template') body.template_id = templateId.value
    if (source.value === 'clone') body.clone_from = cloneFrom.value
    const created = await api.post('/api/servers', body)
    if (created.job) watchJob(created.job, { onDone: () => refreshServers() })
    emit('created', created)
  } catch (e) {
    toastError(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Modal title="New BeamMP server" wide @close="emit('close')">
    <form id="create-server" class="grid gap-4 sm:grid-cols-2" @submit.prevent="submit">
      <div class="sm:col-span-2">
        <label class="label">Start from</label>
        <div class="flex rounded-lg bg-surface-800 p-0.5 text-sm">
          <button v-for="[k, label] in [['blank', 'Blank server'], ['template', 'Template'], ['clone', 'Copy of a server']]" :key="k" type="button"
            class="flex-1 rounded-md px-3 py-1.5" :class="source === k ? 'bg-surface-600 text-slate-100' : 'text-slate-400 hover:text-slate-200'" @click="source = k">{{ label }}</button>
        </div>
      </div>
      <div v-if="source === 'template'" class="sm:col-span-2">
        <select v-model="templateId" class="input" required>
          <option v-for="t in templateList" :key="t.id" :value="t.id">{{ t.name }} ({{ t.mods }} mods, {{ t.plugins }} plugins)</option>
        </select>
        <p class="help">{{ templateList.length ? 'Config, mods and plugins come from the template.' : 'No templates yet. Save one from a server\'s Settings tab.' }}</p>
      </div>
      <div v-if="source === 'clone'" class="sm:col-span-2">
        <select v-model="cloneFrom" class="input" required>
          <option v-for="s in servers.list" :key="s.id" :value="s.id">{{ plainName(s.name) }} (port {{ s.port }})</option>
        </select>
        <p class="help">Copies config (including the auth key), mods and plugins. Bans, backups and schedules are not copied.</p>
      </div>
      <div class="sm:col-span-2">
        <label class="label">Server name</label>
        <input v-model="form.name" class="input" required maxlength="128" placeholder="My BeamMP Server" autofocus />
      </div>
      <div class="sm:col-span-2">
        <label class="label">Auth key</label>
        <input v-model="form.auth_key" class="input font-mono" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" autocomplete="off" />
        <p class="help">{{ source === 'blank' ? '' : 'Leave empty to use the one from the source. ' }}From <a href="https://keymaster.beammp.com" target="_blank" rel="noopener" class="text-accent-400 hover:underline">keymaster.beammp.com</a> → Keys. You can add it later.</p>
      </div>
      <div v-if="source === 'blank'">
        <label class="label">Map</label>
        <select v-model="form.map" class="input">
          <option v-for="[k, label] in maps" :key="k" :value="`/levels/${k}/info.json`">{{ label }}</option>
        </select>
        <p class="help">Modded maps can be picked after uploading them.</p>
      </div>
      <div v-if="source === 'blank'">
        <label class="label">Max players</label>
        <input v-model.number="form.max_players" type="number" min="1" max="500" class="input" />
      </div>
      <div>
        <label class="label">Port</label>
        <input v-model.number="form.port" type="number" class="input" :placeholder="system ? `Auto (${system.port_range[0]}–${system.port_range[1]})` : 'Auto'" />
        <p class="help">TCP and UDP. It must be inside the range published by the container.</p>
      </div>
      <div>
        <label class="label">BeamMP-Server version</label>
        <select v-model="form.version" class="input">
          <option value="latest">{{ source === 'blank' ? 'Latest (auto-updates on restart)' : 'Same as source / latest' }}</option>
          <option v-for="v in versions" :key="v" :value="v">{{ v }}</option>
        </select>
      </div>
    </form>
    <template #footer>
      <button class="btn-ghost" @click="emit('close')">Cancel</button>
      <button class="btn-primary" form="create-server" :disabled="busy || (source === 'template' && !templateId)">Create server</button>
    </template>
  </Modal>
</template>
