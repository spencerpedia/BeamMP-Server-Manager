<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { toast, toastError } from '../store'
import { watchJob } from '../jobs'
import Icon from './Icon.vue'
import Modal from './Modal.vue'

const props = defineProps({ serverId: Number, installed: Object }) // installed: { resourceId: version }
const emit = defineEmits(['close', 'installed'])

const meta = ref({ categories: {}, orders: {} })
const category = ref('')
const order = ref('download_count')
const page = ref(1)
const data = ref({ items: [], pages: 1 })
const loading = ref(false)
const error = ref('')
const url = ref('')
const pending = ref({})

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.get(`/api/browse/mods?category=${encodeURIComponent(category.value)}&order=${order.value}&page=${page.value}`)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  meta.value = await api.get('/api/browse/mods/meta')
  load()
})
watch([category, order], () => {
  page.value = 1
  load()
})
watch(page, load)

async function install(resource, key = resource) {
  pending.value[key] = true
  try {
    const job = await api.post(`/api/servers/${props.serverId}/mods/install`, { resource: String(resource) })
    watchJob(job, {
      onDone: (r) => {
        delete pending.value[key]
        if (r.maps?.length) toast(`${r.title} contains map ${r.maps.join(', ')}. Pick it under Config or Mods.`, 'info')
        emit('installed')
      },
      onError: () => delete pending.value[key],
    })
  } catch (e) {
    delete pending.value[key]
    toastError(e)
  }
}

function installUrl() {
  if (!url.value.trim()) return
  install(url.value.trim(), 'url')
  url.value = ''
}

const compact = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)}k` : String(n))
const pages = computed(() => {
  const last = data.value.pages, cur = page.value
  const set = new Set([1, last, cur - 1, cur, cur + 1].filter((p) => p >= 1 && p <= last))
  return [...set].sort((a, b) => a - b)
})
</script>

<template>
  <Modal title="Browse BeamNG.com mods" xl @close="emit('close')">
    <div class="mb-4 flex flex-wrap items-end gap-3">
      <div>
        <label class="label">Category</label>
        <select v-model="category" class="input w-48">
          <option v-for="(label, key) in meta.categories" :key="key" :value="key">{{ label }}</option>
        </select>
      </div>
      <div>
        <label class="label">Sort</label>
        <select v-model="order" class="input w-48">
          <option v-for="(label, key) in meta.orders" :key="key" :value="key">{{ label }}</option>
        </select>
      </div>
      <form class="ml-auto flex min-w-[18rem] flex-1 gap-2 md:max-w-md" @submit.prevent="installUrl">
        <div class="flex-1">
          <label class="label">Install by link</label>
          <input v-model="url" class="input" placeholder="https://www.beamng.com/resources/…" />
        </div>
        <button class="btn-primary self-end py-2" :disabled="!url.trim() || pending.url"><Icon name="download" :size="14" />Install</button>
      </form>
    </div>
    <p class="mb-4 text-xs text-slate-500">
      Search on <a href="https://www.beamng.com/resources/" target="_blank" rel="noopener" class="text-accent-400 hover:underline">beamng.com/resources</a>
      and paste the link here; keyword search isn't available to tools. Mods go to Resources/Client and are sent to players when they join.
    </p>

    <p v-if="error" class="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">{{ error }}</p>
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" :class="{ 'opacity-50': loading }">
      <div v-for="m in data.items" :key="m.id" class="flex flex-col overflow-hidden rounded-xl border border-surface-700 bg-surface-800">
        <div class="flex gap-3 p-3">
          <img v-if="m.icon" :src="m.icon" alt="" class="h-16 w-16 shrink-0 rounded-lg bg-surface-700 object-cover" loading="lazy" referrerpolicy="no-referrer" />
          <div class="min-w-0">
            <a :href="m.url" target="_blank" rel="noopener" class="line-clamp-2 font-semibold leading-snug text-slate-100 hover:text-accent-400">{{ m.title }}</a>
            <div class="truncate text-xs text-slate-400">{{ m.author }} · v{{ m.version }}</div>
            <span v-if="m.prefix" class="chip mt-1 bg-surface-600 text-[10px] text-slate-300">{{ m.prefix }}</span>
          </div>
        </div>
        <p class="line-clamp-2 flex-1 px-3 text-xs text-slate-400">{{ m.tagline }}</p>
        <div class="mt-2 flex items-center gap-3 border-t border-surface-700 px-3 py-2 text-xs text-slate-400">
          <span title="Downloads"><Icon name="download" :size="12" class="inline" /> {{ compact(m.downloads) }}</span>
          <span v-if="m.rating" title="Rating">★ {{ m.rating.toFixed(1) }}</span>
          <span class="flex-1" />
          <span v-if="installed[m.id] && installed[m.id] === m.version" class="chip bg-emerald-500/15 text-emerald-300">Installed</span>
          <button v-else class="btn-primary px-2 py-1 text-xs" :disabled="pending[m.id]" @click="install(m.id)">
            {{ pending[m.id] ? 'Installing…' : installed[m.id] ? 'Update' : 'Install' }}
          </button>
        </div>
      </div>
    </div>
    <div v-if="loading && !data.items.length" class="py-16 text-center text-slate-500">Loading…</div>

    <div v-if="data.pages > 1" class="mt-4 flex items-center justify-center gap-1 text-sm">
      <button class="btn-ghost px-2 py-1" :disabled="page === 1" @click="page--">‹</button>
      <template v-for="(p, i) in pages" :key="p">
        <span v-if="i && p - pages[i - 1] > 1" class="px-1 text-slate-500">…</span>
        <button class="rounded-md px-2.5 py-1" :class="p === page ? 'bg-accent-500 text-white' : 'text-slate-300 hover:bg-surface-700'" @click="page = p">{{ p }}</button>
      </template>
      <button class="btn-ghost px-2 py-1" :disabled="page === data.pages" @click="page++">›</button>
    </div>
  </Modal>
</template>
