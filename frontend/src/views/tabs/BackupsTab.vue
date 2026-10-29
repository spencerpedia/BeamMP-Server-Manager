<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { api } from '../../api'
import { toast, toastError } from '../../store'
import { bytes, dateTime } from '../../format'
import { confirmDialog } from '../../components/confirm'
import Icon from '../../components/Icon.vue'

const server = inject('server')
const items = ref([])
const busy = ref(false)
const base = computed(() => `/api/servers/${server.value.id}/backups`)

async function load() {
  const r = await api.get(base.value)
  items.value = r.backups
  busy.value = r.busy
}
onMounted(() => load().catch(toastError))

async function create() {
  busy.value = true
  try {
    const b = await api.post(base.value, { label: 'manual' })
    toast(`Backup ${b.name} created`, 'success')
  } catch (e) {
    toastError(e)
  } finally {
    await load()
  }
}

async function restore(b) {
  if (server.value.state !== 'stopped' && server.value.state !== 'crashed') {
    toast('Stop the server before restoring', 'error')
    return
  }
  const ok = await confirmDialog(`Restore ${b.name}?\n\nThis replaces the server's config, mods and plugins with the backup's contents.`, { danger: true, confirmText: 'Restore' })
  if (!ok) return
  busy.value = true
  try {
    await api.post(`${base.value}/${b.name}/restore`)
    toast('Backup restored', 'success')
  } catch (e) {
    toastError(e)
  } finally {
    await load()
  }
}

async function remove(b) {
  if (!(await confirmDialog(`Delete backup ${b.name}?`, { danger: true, confirmText: 'Delete' }))) return
  await api.del(`${base.value}/${b.name}`).catch(toastError)
  await load()
}
</script>

<template>
  <div class="card">
    <div class="flex items-center justify-between border-b border-surface-700 px-5 py-3">
      <div>
        <h2 class="font-semibold">Backups</h2>
        <p class="text-xs text-slate-500">
          Keeps the newest {{ server.backup_retention || 'unlimited' }} backups (change under Settings). Schedule automatic backups on the Schedules tab.
        </p>
      </div>
      <button v-if="server.can_control" class="btn-primary" :disabled="busy" @click="create"><Icon name="archive" />{{ busy ? 'Working…' : 'Back up now' }}</button>
    </div>
    <table class="table">
      <thead><tr><th>Backup</th><th>Created</th><th>Size</th><th></th></tr></thead>
      <tbody>
        <tr v-for="b in items" :key="b.name">
          <td class="font-mono text-xs text-slate-200">{{ b.name }}</td>
          <td class="text-slate-400">{{ dateTime(b.created) }}</td>
          <td class="text-slate-400">{{ bytes(b.size) }}</td>
          <td class="whitespace-nowrap text-right">
            <template v-if="server.can_control">
              <a class="btn-ghost mr-1 py-1 text-xs" :href="`${base}/${b.name}`" download title="Download"><Icon name="download" :size="12" /></a>
              <button class="btn-ghost mr-1 py-1 text-xs" :disabled="busy" @click="restore(b)"><Icon name="history" :size="12" />Restore</button>
              <button class="btn-ghost py-1 text-xs text-red-300" @click="remove(b)" title="Delete"><Icon name="trash" :size="12" /></button>
            </template>
          </td>
        </tr>
        <tr v-if="!items.length"><td colspan="4" class="py-8 text-center text-slate-500">No backups yet</td></tr>
      </tbody>
    </table>
  </div>
</template>
