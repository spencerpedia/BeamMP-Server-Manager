<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { store } from '../store'

const route = useRoute()
const router = useRouter()
const needsSetup = ref(false)
const username = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const busy = ref(false)

onMounted(async () => {
  needsSetup.value = (await api.get('/api/auth/status')).needs_setup
})

async function submit() {
  error.value = ''
  if (needsSetup.value && password.value !== confirm.value) {
    error.value = 'Passwords do not match'
    return
  }
  busy.value = true
  try {
    const body = { username: username.value, password: password.value }
    store.user = await api.post(needsSetup.value ? '/api/auth/setup' : '/api/auth/login', body)
    router.replace(route.query.next || '/')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="flex min-h-full items-center justify-center bg-[radial-gradient(ellipse_at_top,_#1f2a40_0%,_#0b0f17_60%)] p-4">
    <form class="card w-full max-w-sm p-8 shadow-2xl" @submit.prevent="submit">
      <div class="mb-6 flex flex-col items-center text-center">
        <img src="/favicon.svg" class="mb-3 h-14 w-14" alt="" />
        <h1 class="text-xl font-bold text-slate-100">BeamMP Server Manager</h1>
        <p class="mt-1 text-sm text-slate-400">{{ needsSetup ? 'Create the first admin account' : 'Sign in to continue' }}</p>
      </div>
      <label class="label" for="u">Username</label>
      <input id="u" v-model="username" class="input mb-4" autocomplete="username" required autofocus />
      <label class="label" for="p">Password</label>
      <input id="p" v-model="password" type="password" class="input mb-4" :autocomplete="needsSetup ? 'new-password' : 'current-password'" required :minlength="needsSetup ? 8 : 1" />
      <template v-if="needsSetup">
        <label class="label" for="c">Confirm password</label>
        <input id="c" v-model="confirm" type="password" class="input mb-4" autocomplete="new-password" required />
      </template>
      <p v-if="error" class="mb-4 rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-300">{{ error }}</p>
      <button class="btn-primary w-full py-2" :disabled="busy">{{ needsSetup ? 'Create account' : 'Sign in' }}</button>
    </form>
  </div>
</template>
