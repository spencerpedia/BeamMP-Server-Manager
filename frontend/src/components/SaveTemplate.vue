<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { toastError } from '../store'
import { watchJob } from '../jobs'
import { plainName } from '../format'
import { servers } from '../servers'
import Modal from './Modal.vue'
import Toggle from './Toggle.vue'

const props = defineProps({ serverId: Number })
const emit = defineEmits(['close', 'saved'])
const form = ref({ server_id: props.serverId || servers.list[0]?.id, name: '', description: '', include_auth_key: false })

async function save() {
  try {
    const job = await api.post('/api/templates', form.value)
    watchJob(job, { onDone: (t) => emit('saved', t) })
    emit('close')
  } catch (e) {
    toastError(e)
  }
}
</script>

<template>
  <Modal title="Save as template" @close="emit('close')">
    <form id="save-template" class="space-y-4" @submit.prevent="save">
      <div v-if="!props.serverId">
        <label class="label">Server</label>
        <select v-model="form.server_id" class="input">
          <option v-for="s in servers.list" :key="s.id" :value="s.id">{{ plainName(s.name) }}</option>
        </select>
      </div>
      <div>
        <label class="label">Template name</label>
        <input v-model="form.name" class="input" required maxlength="128" placeholder="Drift night on Utah" />
      </div>
      <div>
        <label class="label">Description</label>
        <textarea v-model="form.description" class="input" rows="2" />
      </div>
      <div class="flex items-center justify-between rounded-lg bg-surface-800 px-4 py-3">
        <div>
          <div class="text-sm font-medium">Include auth key</div>
          <div class="text-xs text-slate-500">Leave off if you'll share the exported template.</div>
        </div>
        <Toggle v-model="form.include_auth_key" />
      </div>
      <p class="text-xs text-slate-500">Saves the config, mods (enabled and disabled) and plugins. Bans, backups and schedules aren't included.</p>
    </form>
    <template #footer>
      <button class="btn-ghost" @click="emit('close')">Cancel</button>
      <button class="btn-primary" form="save-template">Save template</button>
    </template>
  </Modal>
</template>
