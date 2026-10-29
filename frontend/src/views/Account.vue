<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { store, toast, toastError } from '../store'

const form = ref({ current_password: '', new_password: '', confirm: '' })

async function save() {
  if (form.value.new_password !== form.value.confirm) {
    toast('Passwords do not match', 'error')
    return
  }
  try {
    await api.post('/api/auth/password', { current_password: form.value.current_password, new_password: form.value.new_password })
    form.value = { current_password: '', new_password: '', confirm: '' }
    toast('Password changed', 'success')
  } catch (e) {
    toastError(e)
  }
}
</script>

<template>
  <div class="mx-auto max-w-lg p-4 md:p-8">
    <h1 class="mb-1 text-2xl font-bold">Account</h1>
    <p class="mb-6 text-sm text-slate-400">Signed in as <b>{{ store.user.username }}</b> ({{ store.user.role }})</p>
    <form class="card space-y-4 p-5" @submit.prevent="save">
      <h2 class="font-semibold">Change password</h2>
      <div><label class="label">Current password</label><input v-model="form.current_password" type="password" class="input" required autocomplete="current-password" /></div>
      <div><label class="label">New password</label><input v-model="form.new_password" type="password" class="input" required minlength="8" autocomplete="new-password" /></div>
      <div><label class="label">Confirm new password</label><input v-model="form.confirm" type="password" class="input" required autocomplete="new-password" /></div>
      <div class="flex justify-end"><button class="btn-primary">Update password</button></div>
    </form>
  </div>
</template>
