<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { store, toast, toastError } from '../store'
import { servers } from '../servers'
import { dateTime, plainName } from '../format'
import { confirmDialog } from '../components/confirm'
import Icon from '../components/Icon.vue'
import Modal from '../components/Modal.vue'

const users = ref([])
const editing = ref(null)
const ROLES = {
  admin: 'Full access to everything, including users and creating/deleting servers.',
  operator: 'Can control and configure the servers they are given.',
  viewer: 'Read-only: console, players and metrics of the servers they are given.',
}
const roleChip = { admin: 'bg-accent-500/15 text-accent-400', operator: 'bg-sky-500/15 text-sky-300', viewer: 'bg-slate-500/15 text-slate-300' }

const load = async () => (users.value = await api.get('/api/users'))
onMounted(() => load().catch(toastError))

const serverName = (id) => plainName(servers.list.find((s) => s.id === id)?.name || `#${id}`)

async function save() {
  const u = editing.value
  try {
    if (u.id) {
      const body = { role: u.role, server_ids: u.server_ids }
      if (u.password) body.password = u.password
      await api.patch(`/api/users/${u.id}`, body)
    } else {
      await api.post('/api/users', u)
    }
    editing.value = null
    await load()
    toast('User saved', 'success')
  } catch (e) {
    toastError(e)
  }
}

async function remove(u) {
  if (!(await confirmDialog(`Delete user ${u.username}?`, { danger: true, confirmText: 'Delete' }))) return
  await api.del(`/api/users/${u.id}`).catch(toastError)
  await load()
}
</script>

<template>
  <div class="mx-auto max-w-5xl p-4 md:p-8">
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">Users</h1>
        <p class="text-sm text-slate-400">Who can sign in, and which servers they can see or control</p>
      </div>
      <button class="btn-primary" @click="editing = { username: '', password: '', role: 'operator', server_ids: [] }"><Icon name="plus" />Add user</button>
    </div>
    <div class="card overflow-x-auto">
      <table class="table">
        <thead><tr><th>User</th><th>Role</th><th>Servers</th><th>Created</th><th></th></tr></thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td class="font-medium text-slate-100">{{ u.username }} <span v-if="u.id === store.user.id" class="text-xs text-slate-500">(you)</span></td>
            <td><span class="chip capitalize" :class="roleChip[u.role]">{{ u.role }}</span></td>
            <td class="text-xs text-slate-400">
              <template v-if="u.role === 'admin'">All servers</template>
              <template v-else-if="u.server_ids.length">{{ u.server_ids.map(serverName).join(', ') }}</template>
              <span v-else class="text-amber-400">None</span>
            </td>
            <td class="text-xs text-slate-500">{{ dateTime(u.created_at) }}</td>
            <td class="whitespace-nowrap text-right">
              <button class="btn-ghost mr-1 py-1 text-xs" @click="editing = { ...u, password: '' }"><Icon name="edit" :size="12" /></button>
              <button v-if="u.id !== store.user.id" class="btn-ghost py-1 text-xs text-red-300" @click="remove(u)"><Icon name="trash" :size="12" /></button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <Modal v-if="editing" :title="editing.id ? `Edit ${editing.username}` : 'Add user'" @close="editing = null">
      <form id="user" class="space-y-4" @submit.prevent="save">
        <div v-if="!editing.id">
          <label class="label">Username</label>
          <input v-model="editing.username" class="input" required autocomplete="off" />
        </div>
        <div>
          <label class="label">{{ editing.id ? 'New password (leave blank to keep)' : 'Password' }}</label>
          <input v-model="editing.password" type="password" class="input" :required="!editing.id" minlength="8" autocomplete="new-password" />
        </div>
        <div>
          <label class="label">Role</label>
          <div class="space-y-2">
            <label v-for="(desc, role) in ROLES" :key="role" class="flex cursor-pointer gap-3 rounded-lg border px-3 py-2" :class="editing.role === role ? 'border-accent-500 bg-accent-500/5' : 'border-surface-600'">
              <input v-model="editing.role" type="radio" :value="role" class="mt-1 accent-orange-500" />
              <span><span class="block text-sm font-medium capitalize">{{ role }}</span><span class="text-xs text-slate-400">{{ desc }}</span></span>
            </label>
          </div>
        </div>
        <div v-if="editing.role !== 'admin'">
          <label class="label">Servers</label>
          <div class="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-surface-600 p-2">
            <label v-for="s in servers.list" :key="s.id" class="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-surface-800">
              <input v-model="editing.server_ids" type="checkbox" :value="s.id" class="accent-orange-500" />{{ plainName(s.name) }}
            </label>
            <p v-if="!servers.list.length" class="px-2 text-xs text-slate-500">No servers yet</p>
          </div>
        </div>
      </form>
      <template #footer>
        <button class="btn-ghost" @click="editing = null">Cancel</button>
        <button class="btn-primary" form="user">Save</button>
      </template>
    </Modal>
  </div>
</template>
