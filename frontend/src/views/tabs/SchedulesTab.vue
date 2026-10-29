<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { api } from '../../api'
import { toast, toastError } from '../../store'
import { dateTime, timeAgo } from '../../format'
import { confirmDialog } from '../../components/confirm'
import Icon from '../../components/Icon.vue'
import Modal from '../../components/Modal.vue'
import Toggle from '../../components/Toggle.vue'

const server = inject('server')
const schedules = ref([])
const editing = ref(null)
const base = computed(() => `/api/servers/${server.value.id}/schedules`)

const ACTIONS = {
  restart: 'Restart server',
  backup: 'Create backup',
  command: 'Run console command',
  update: 'Update BeamMP-Server and restart',
  start: 'Start server',
  stop: 'Stop server',
}
const PRESETS = [
  ['Every day at 4:00', '0 4 * * *'],
  ['Every 6 hours', '0 */6 * * *'],
  ['Every hour', '0 * * * *'],
  ['Every 15 minutes', '*/15 * * * *'],
  ['Mondays at 5:00', '0 5 * * 1'],
]

const load = async () => (schedules.value = await api.get(base.value))
onMounted(() => load().catch(toastError))

function create() {
  editing.value = { name: '', action: 'restart', cron: '0 4 * * *', payload: '', warn_minutes: 5, enabled: true }
}

async function save() {
  const s = editing.value
  try {
    if (s.id) await api.put(`${base.value}/${s.id}`, s)
    else await api.post(base.value, s)
    editing.value = null
    await load()
    toast('Schedule saved', 'success')
  } catch (e) {
    toastError(e)
  }
}

async function toggle(s) {
  try {
    await api.put(`${base.value}/${s.id}`, { ...s, enabled: !s.enabled })
    await load()
  } catch (e) {
    toastError(e)
  }
}

async function remove(s) {
  if (!(await confirmDialog(`Delete the schedule "${s.name || ACTIONS[s.action]}"?`, { danger: true, confirmText: 'Delete' }))) return
  await api.del(`${base.value}/${s.id}`).catch(toastError)
  await load()
}

async function runNow(s) {
  try {
    await api.post(`${base.value}/${s.id}/run`)
    toast('Started. Check the console for the result.')
    setTimeout(load, 3000)
  } catch (e) {
    toastError(e)
  }
}

const warnable = (a) => ['restart', 'stop', 'update'].includes(a)
</script>

<template>
  <div class="card">
    <div class="flex items-center justify-between border-b border-surface-700 px-5 py-3">
      <div>
        <h2 class="font-semibold">Scheduled tasks</h2>
        <p class="text-xs text-slate-500">Times use the container's timezone (set TZ on the container).</p>
      </div>
      <button v-if="server.can_control" class="btn-primary" @click="create"><Icon name="plus" />New schedule</button>
    </div>
    <div class="overflow-x-auto">
      <table class="table">
        <thead><tr><th>Task</th><th>When</th><th>Next run</th><th>Last run</th><th>Enabled</th><th></th></tr></thead>
        <tbody>
          <tr v-for="s in schedules" :key="s.id" :class="{ 'opacity-60': !s.enabled }">
            <td>
              <div class="font-medium text-slate-100">{{ s.name || ACTIONS[s.action] }}</div>
              <div class="text-xs text-slate-500">
                {{ ACTIONS[s.action] }}<template v-if="s.action === 'command'">: <code class="text-slate-400">{{ s.payload }}</code></template>
                <template v-if="warnable(s.action) && s.warn_minutes"> · {{ s.warn_minutes }} min warning</template>
              </div>
            </td>
            <td class="font-mono text-xs">{{ s.cron }}</td>
            <td class="whitespace-nowrap text-xs text-slate-400" :title="dateTime(s.next_run)">{{ s.next_run ? timeAgo(s.next_run) : '—' }}</td>
            <td class="text-xs">
              <div class="text-slate-400">{{ timeAgo(s.last_run) }}</div>
              <div v-if="s.last_result" class="max-w-[16rem] truncate" :class="s.last_result.startsWith('error') ? 'text-red-400' : 'text-slate-500'" :title="s.last_result">{{ s.last_result }}</div>
            </td>
            <td><Toggle :model-value="s.enabled" :disabled="!server.can_control" @update:model-value="toggle(s)" /></td>
            <td class="whitespace-nowrap text-right">
              <template v-if="server.can_control">
                <button class="btn-ghost mr-1 py-1 text-xs" @click="runNow(s)" title="Run now"><Icon name="play" :size="12" /></button>
                <button class="btn-ghost mr-1 py-1 text-xs" @click="editing = { ...s }" title="Edit"><Icon name="edit" :size="12" /></button>
                <button class="btn-ghost py-1 text-xs text-red-300" @click="remove(s)" title="Delete"><Icon name="trash" :size="12" /></button>
              </template>
            </td>
          </tr>
          <tr v-if="!schedules.length"><td colspan="6" class="py-8 text-center text-slate-500">No schedules. Add a nightly restart or backup.</td></tr>
        </tbody>
      </table>
    </div>

    <Modal v-if="editing" :title="editing.id ? 'Edit schedule' : 'New schedule'" wide @close="editing = null">
      <form id="sched" class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
        <div>
          <label class="label">Action</label>
          <select v-model="editing.action" class="input">
            <option v-for="(label, key) in ACTIONS" :key="key" :value="key">{{ label }}</option>
          </select>
        </div>
        <div>
          <label class="label">Name (optional)</label>
          <input v-model="editing.name" class="input" :placeholder="ACTIONS[editing.action]" />
        </div>
        <div v-if="editing.action === 'command'" class="sm:col-span-2">
          <label class="label">Console command(s)</label>
          <textarea v-model="editing.payload" rows="3" class="input font-mono" placeholder="say Remember to join our Discord!" required />
          <p class="help">One command per line.</p>
        </div>
        <div class="sm:col-span-2">
          <label class="label">Cron expression</label>
          <input v-model="editing.cron" class="input font-mono" required />
          <div class="mt-2 flex flex-wrap gap-1.5">
            <button v-for="[label, expr] in PRESETS" :key="expr" type="button" class="chip bg-surface-700 text-slate-300 hover:bg-surface-600" @click="editing.cron = expr">{{ label }}</button>
          </div>
          <p class="help">minute hour day-of-month month day-of-week</p>
        </div>
        <div v-if="warnable(editing.action)">
          <label class="label">In-game warning (minutes)</label>
          <input v-model.number="editing.warn_minutes" type="number" min="0" max="60" class="input" />
          <p class="help">Counts down in chat before acting. Skipped if nobody is online.</p>
        </div>
        <div class="flex items-center gap-3 self-end pb-2">
          <Toggle v-model="editing.enabled" /><span class="text-sm">Enabled</span>
        </div>
      </form>
      <template #footer>
        <button class="btn-ghost" @click="editing = null">Cancel</button>
        <button class="btn-primary" form="sched">Save</button>
      </template>
    </Modal>
  </div>
</template>
