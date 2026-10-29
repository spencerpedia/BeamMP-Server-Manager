<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { api } from '../../api'
import { toast, toastError } from '../../store'
import { refreshServers } from '../../servers'
import Icon from '../../components/Icon.vue'
import Toggle from '../../components/Toggle.vue'

const server = inject('server')
const fields = ref([])
const values = ref({})
const original = ref('')
const maps = ref([])
const raw = ref('')
const mode = ref('form')
const showKey = ref(false)
const busy = ref(false)
const readonly = computed(() => !server.value.can_control)
const dirty = computed(() => JSON.stringify(values.value) !== original.value)

async function load() {
  const cfg = await api.get(`/api/servers/${server.value.id}/config`)
  fields.value = cfg.fields
  values.value = cfg.values
  original.value = JSON.stringify(cfg.values)
  maps.value = (await api.get(`/api/servers/${server.value.id}/maps`)).maps
  if (server.value.can_control) raw.value = (await api.get(`/api/servers/${server.value.id}/config/raw`)).text
}
onMounted(() => load().catch(toastError))

const mapOptions = computed(() => {
  const opts = maps.value.map((m) => ({ value: m.path, label: m.source === 'builtin' ? m.label : `${m.label} (${m.source}${m.enabled === false ? ', disabled' : ''})` }))
  if (values.value.Map && !opts.some((o) => o.value === values.value.Map)) opts.unshift({ value: values.value.Map, label: `${values.value.Map} (not found)` })
  return opts
})

async function saveForm() {
  busy.value = true
  try {
    const body = {}
    for (const f of fields.value) body[f.key] = values.value[f.key]
    const r = await api.put(`/api/servers/${server.value.id}/config`, body)
    toast(r.restart_required ? 'Saved. Restart the server to apply.' : 'Saved', 'success')
    await load()
    refreshServers()
  } catch (e) {
    toastError(e)
  } finally {
    busy.value = false
  }
}

async function saveRaw() {
  busy.value = true
  try {
    const r = await api.put(`/api/servers/${server.value.id}/config/raw`, { text: raw.value })
    toast(r.restart_required ? 'Saved. Restart the server to apply.' : 'Saved', 'success')
    await load()
    refreshServers()
  } catch (e) {
    toastError(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="card">
    <div class="flex items-center justify-between border-b border-surface-700 px-5 py-3">
      <div class="text-sm text-slate-400">ServerConfig.toml</div>
      <div v-if="server.can_control" class="flex rounded-lg bg-surface-800 p-0.5 text-xs">
        <button class="rounded-md px-3 py-1" :class="mode === 'form' ? 'bg-surface-600 text-slate-100' : 'text-slate-400'" @click="mode = 'form'">Form</button>
        <button class="rounded-md px-3 py-1" :class="mode === 'raw' ? 'bg-surface-600 text-slate-100' : 'text-slate-400'" @click="mode = 'raw'">Raw TOML</button>
      </div>
    </div>

    <form v-if="mode === 'form'" class="grid gap-x-6 gap-y-5 p-5 md:grid-cols-2" @submit.prevent="saveForm">
      <div v-for="f in fields" :key="f.key" :class="{ 'md:col-span-2': ['text', 'secret'].includes(f.type) }">
        <template v-if="f.type === 'bool'">
          <div class="flex items-center justify-between gap-4 rounded-lg bg-surface-800 px-4 py-3">
            <div>
              <div class="text-sm font-medium text-slate-200">{{ f.label }}</div>
              <div v-if="f.help" class="text-xs text-slate-500">{{ f.help }}</div>
            </div>
            <Toggle v-model="values[f.key]" :disabled="readonly" />
          </div>
        </template>
        <template v-else>
          <label class="label">{{ f.label }}</label>
          <textarea v-if="f.type === 'text'" v-model="values[f.key]" rows="2" class="input" :disabled="readonly" />
          <div v-else-if="f.type === 'secret'" class="flex gap-2">
            <input v-model="values[f.key]" :type="showKey ? 'text' : 'password'" class="input font-mono" autocomplete="off" :disabled="readonly" />
            <button type="button" class="btn-ghost" @click="showKey = !showKey" :title="showKey ? 'Hide' : 'Show'"><Icon :name="showKey ? 'eyeoff' : 'eye'" /></button>
          </div>
          <select v-else-if="f.type === 'map'" v-model="values[f.key]" class="input" :disabled="readonly">
            <option v-for="o in mapOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
          <input v-else-if="f.type === 'int'" v-model.number="values[f.key]" type="number" :min="f.min" :max="f.max" class="input" :disabled="readonly" />
          <input v-else v-model="values[f.key]" class="input" :disabled="readonly" />
          <p v-if="f.help" class="help">{{ f.help }}</p>
        </template>
      </div>
      <div class="flex items-center justify-between gap-3 md:col-span-2">
        <p class="text-xs text-slate-500">Port and ResourceFolder are managed by the panel. Change the port under Settings.</p>
        <button v-if="server.can_control" class="btn-primary" :disabled="busy || !dirty">Save changes</button>
      </div>
    </form>

    <div v-else class="p-5">
      <textarea v-model="raw" spellcheck="false" class="input h-[55vh] font-mono text-xs leading-relaxed" />
      <div class="mt-3 flex justify-end">
        <button class="btn-primary" :disabled="busy" @click="saveRaw">Save TOML</button>
      </div>
    </div>
  </div>
</template>
