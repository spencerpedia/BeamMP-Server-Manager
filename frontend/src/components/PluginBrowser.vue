<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { toast, toastError } from '../store'
import { watchJob } from '../jobs'
import Icon from './Icon.vue'
import Modal from './Modal.vue'

const props = defineProps({ serverId: Number })
const emit = defineEmits(['close', 'installed'])
const featured = ref([])
const results = ref(null)
const q = ref('')
const loading = ref(false)
const pending = ref({})
const repoInput = ref('')

onMounted(async () => {
  try {
    featured.value = await api.get('/api/browse/plugins/featured')
  } catch (e) {
    toastError(e)
  }
})

async function search() {
  loading.value = true
  try {
    results.value = await api.get(`/api/browse/plugins?q=${encodeURIComponent(q.value)}`)
  } catch (e) {
    toastError(e)
  } finally {
    loading.value = false
  }
}

async function install(repo) {
  pending.value[repo] = true
  try {
    const job = await api.post(`/api/servers/${props.serverId}/plugins/install`, { repo })
    watchJob(job, {
      quiet: true,
      onDone: (r) => {
        delete pending.value[repo]
        const parts = []
        if (r.plugins.length) parts.push(`plugins ${r.plugins.join(', ')}`)
        if (r.mods.length) parts.push(`client mods ${r.mods.join(', ')}`)
        toast(`Installed ${repo} (${r.source}): ${parts.join(' and ')}`, 'success')
        emit('installed')
      },
      onError: () => delete pending.value[repo],
    })
  } catch (e) {
    delete pending.value[repo]
    toastError(e)
  }
}

const ago = (d) => (d ? new Date(d).toLocaleDateString() : '')
</script>

<template>
  <Modal title="Browse BeamMP plugins" xl @close="emit('close')">
    <div class="mb-4 flex flex-wrap gap-3">
      <form class="flex flex-1 gap-2" @submit.prevent="search">
        <input v-model="q" class="input" placeholder="Search GitHub for BeamMP plugins (race, admin, economy…)" />
        <button class="btn-primary" :disabled="loading"><Icon name="list" :size="14" />Search</button>
      </form>
      <form class="flex gap-2" @submit.prevent="repoInput.trim() && install(repoInput.trim())">
        <input v-model="repoInput" class="input w-64" placeholder="owner/repo or GitHub link" />
        <button class="btn-ghost" :disabled="!repoInput.trim()">Install</button>
      </form>
    </div>
    <p class="mb-4 text-xs text-slate-500">
      Plugins come from GitHub: the latest release zip if there is one, otherwise the main branch. The panel detects the layout and installs
      server plugins to Resources/Server and any client parts to Resources/Client. Only install plugins you trust; they run on your server.
    </p>

    <template v-for="section in [results ? { title: `Search results (${results.total})`, items: results.items } : null, { title: 'Featured', items: featured }]" :key="section?.title">
      <div v-if="section" class="mb-6">
        <h3 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">{{ section.title }}</h3>
        <div class="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          <div v-for="r in section.items" :key="r.full_name" class="flex flex-col rounded-xl border border-surface-700 bg-surface-800 p-4">
            <div class="flex items-start gap-3">
              <img v-if="r.owner_avatar" :src="r.owner_avatar" alt="" class="h-9 w-9 rounded-full" loading="lazy" />
              <div class="min-w-0 flex-1">
                <a :href="r.url" target="_blank" rel="noopener" class="block truncate font-semibold text-slate-100 hover:text-accent-400">{{ r.full_name.split('/')[1] }}</a>
                <div class="truncate text-xs text-slate-500">{{ r.full_name.split('/')[0] }}</div>
              </div>
              <span v-if="r.stars != null" class="text-xs text-slate-400">★ {{ r.stars }}</span>
            </div>
            <p class="mt-2 line-clamp-2 flex-1 text-sm text-slate-400">{{ r.description || 'No description' }}</p>
            <div class="mt-3 flex items-center text-xs text-slate-500">
              <span>{{ r.archived ? 'Archived · ' : '' }}{{ r.updated ? `Updated ${ago(r.updated)}` : '' }}</span>
              <span class="flex-1" />
              <button class="btn-primary px-2 py-1 text-xs" :disabled="pending[r.full_name]" @click="install(r.full_name)">
                {{ pending[r.full_name] ? 'Installing…' : 'Install' }}
              </button>
            </div>
          </div>
          <p v-if="!section.items.length" class="text-sm text-slate-500">Nothing found.</p>
        </div>
      </div>
    </template>
  </Modal>
</template>
