<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { store } from './store'
import { servers, connectServers, disconnectServers } from './servers'
import { plainName } from './format'
import Icon from './components/Icon.vue'
import Toasts from './components/Toasts.vue'
import ConfirmHost from './components/ConfirmHost.vue'
import JobsTray from './components/JobsTray.vue'

const route = useRoute()
const router = useRouter()
const mobileNav = ref(false)
const showShell = computed(() => store.user && !route.meta.public)

watch(
  () => store.user,
  (u) => (u ? connectServers() : disconnectServers()),
  { immediate: true },
)
watch(() => route.fullPath, () => (mobileNav.value = false))

const dot = (state) =>
  ({ running: 'bg-emerald-400', starting: 'bg-amber-400 animate-pulse', stopping: 'bg-amber-400 animate-pulse', crashed: 'bg-red-400' })[state] ||
  'bg-slate-600'

async function logout() {
  await api.post('/api/auth/logout')
  store.user = null
  router.push('/login')
}
</script>

<template>
  <div v-if="showShell" class="flex h-full">
    <aside
      class="fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-surface-700 bg-surface-900 transition-transform md:static md:translate-x-0"
      :class="mobileNav ? 'translate-x-0' : '-translate-x-full'"
    >
      <RouterLink to="/" class="flex items-center gap-2.5 px-5 py-4">
        <img src="/favicon.svg" class="h-8 w-8" alt="" />
        <div class="leading-tight">
          <div class="font-bold text-slate-100">BeamMP</div>
          <div class="text-xs text-slate-400">Server Manager</div>
        </div>
      </RouterLink>

      <nav class="flex-1 overflow-y-auto px-3 py-2 text-sm">
        <RouterLink to="/" class="nav-link" exact-active-class="nav-active"><Icon name="layers" />Dashboard</RouterLink>

        <div class="mb-1 mt-5 px-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Servers</div>
        <RouterLink
          v-for="s in servers.list"
          :key="s.id"
          :to="`/servers/${s.id}`"
          class="nav-link"
          :class="{ 'nav-active': route.params.id == s.id }"
        >
          <span class="h-2 w-2 shrink-0 rounded-full" :class="dot(s.state)" />
          <span class="truncate">{{ plainName(s.name) }}</span>
          <span v-if="s.state === 'running'" class="ml-auto text-xs text-slate-500">{{ s.players?.length || 0 }}/{{ s.max_players }}</span>
        </RouterLink>
        <p v-if="servers.loaded && !servers.list.length" class="px-3 py-1 text-xs text-slate-500">No servers yet</p>

        <template v-if="store.user.role === 'admin'">
          <div class="mb-1 mt-5 px-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Admin</div>
          <RouterLink to="/admin/templates" class="nav-link" active-class="nav-active"><Icon name="layers" />Templates</RouterLink>
          <RouterLink to="/admin/import" class="nav-link" active-class="nav-active"><Icon name="download" />Import servers</RouterLink>
          <RouterLink to="/admin/users" class="nav-link" active-class="nav-active"><Icon name="users" />Users</RouterLink>
          <RouterLink to="/admin/versions" class="nav-link" active-class="nav-active"><Icon name="package" />BeamMP versions</RouterLink>
          <RouterLink to="/admin/audit" class="nav-link" active-class="nav-active"><Icon name="history" />Audit log</RouterLink>
        </template>
      </nav>

      <div class="flex items-center gap-2 border-t border-surface-700 px-4 py-3 text-sm">
        <RouterLink to="/account" class="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1 py-1 hover:bg-surface-800">
          <span class="flex h-8 w-8 items-center justify-center rounded-full bg-surface-700 text-slate-300"><Icon name="user" /></span>
          <span class="min-w-0">
            <span class="block truncate font-medium text-slate-200">{{ store.user.username }}</span>
            <span class="block text-xs capitalize text-slate-500">{{ store.user.role }}</span>
          </span>
        </RouterLink>
        <button class="rounded-lg p-2 text-slate-400 hover:bg-surface-800 hover:text-slate-100" title="Log out" @click="logout">
          <Icon name="logout" />
        </button>
      </div>
    </aside>
    <div v-if="mobileNav" class="fixed inset-0 z-20 bg-black/50 md:hidden" @click="mobileNav = false" />

    <main class="min-w-0 flex-1 overflow-y-auto">
      <div class="flex items-center gap-3 border-b border-surface-700 bg-surface-900 px-4 py-3 md:hidden">
        <button class="text-slate-300" @click="mobileNav = true" aria-label="Open menu"><Icon name="menu" :size="20" /></button>
        <span class="font-semibold">BeamMP Server Manager</span>
      </div>
      <div v-if="!servers.connected && servers.loaded" class="bg-amber-500/10 px-4 py-1.5 text-center text-xs text-amber-300">
        Live connection lost, reconnecting…
      </div>
      <RouterView />
    </main>
  </div>
  <RouterView v-else />
  <Toasts />
  <ConfirmHost />
  <JobsTray v-if="store.user" />
</template>

<style>
.nav-link {
  @apply mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-slate-300 transition hover:bg-surface-800 hover:text-slate-100;
}
.nav-active {
  @apply bg-accent-500/10 text-accent-400 hover:bg-accent-500/15 hover:text-accent-400;
}
</style>
