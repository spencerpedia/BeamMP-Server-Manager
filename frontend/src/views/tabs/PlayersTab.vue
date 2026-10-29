<script setup>
import { computed, inject, nextTick, onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import { toast, toastError } from '../../store'
import { dateTime, plainName } from '../../format'
import Icon from '../../components/Icon.vue'
import Modal from '../../components/Modal.vue'

const server = inject('server')
const live = inject('live')
const bans = ref([])
const chatFilter = ref('')
const chatBox = ref(null)
const action = ref(null) // { kind: 'kick' | 'ban', player }
const reason = ref('')
const manualBan = ref({ name: '', beammp_id: '', ip: '', reason: '' })
const base = computed(() => `/api/servers/${server.value.id}`)

const loadBans = async () => (bans.value = await api.get(`${base.value}/bans`))
onMounted(() => loadBans().catch(toastError))

const chat = computed(() => {
  const q = chatFilter.value.toLowerCase()
  return q ? live.chat.filter((c) => c.name.toLowerCase().includes(q) || c.message.toLowerCase().includes(q)) : live.chat
})
watch(
  () => live.chat.length,
  async () => {
    await nextTick()
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  },
)

function open(kind, player) {
  action.value = { kind, player }
  reason.value = ''
}

async function confirmAction() {
  const { kind, player } = action.value
  try {
    if (kind === 'kick') {
      await api.post(`${base.value}/players/${player.id}/kick`, { reason: reason.value })
      toast(`Kicked ${player.name}`, 'success')
    } else {
      await api.post(`${base.value}/bans`, { name: player.name, beammp_id: player.beammp || '', reason: reason.value })
      toast(`Banned ${player.name}`, 'success')
      await loadBans()
    }
    action.value = null
  } catch (e) {
    toastError(e)
  }
}

async function addBan() {
  try {
    await api.post(`${base.value}/bans`, manualBan.value)
    manualBan.value = { name: '', beammp_id: '', ip: '', reason: '' }
    await loadBans()
    toast('Ban added', 'success')
  } catch (e) {
    toastError(e)
  }
}

async function unban(b) {
  try {
    await api.del(`${base.value}/bans/${b.id}`)
    await loadBans()
  } catch (e) {
    toastError(e)
  }
}

async function say(msg) {
  if (!msg.trim()) return
  try {
    await api.post(`${base.value}/console`, { command: `say ${msg}` })
    sayText.value = ''
  } catch (e) {
    toastError(e)
  }
}
const sayText = ref('')
const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
</script>

<template>
  <div class="grid gap-4 lg:grid-cols-5">
    <div class="card lg:col-span-3">
      <div class="flex items-center justify-between border-b border-surface-700 px-5 py-3">
        <h2 class="font-semibold">Online players</h2>
        <span class="text-xs text-slate-500">{{ live.players.length }} / {{ server.max_players }}</span>
      </div>
      <table class="table">
        <thead><tr><th>Player</th><th>BeamMP ID</th><th>Cars</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in live.players" :key="p.id">
            <td>
              <span class="font-medium text-slate-100">{{ plainName(p.name) }}</span>
              <span v-if="p.guest" class="chip ml-2 bg-surface-700 text-slate-400">guest</span>
              <div v-if="server.can_control && p.ip" class="text-xs text-slate-500">{{ p.ip }}</div>
            </td>
            <td class="font-mono text-xs text-slate-400">{{ p.beammp || '—' }}</td>
            <td>{{ p.cars }}</td>
            <td class="whitespace-nowrap text-right">
              <template v-if="server.can_control">
                <button class="btn-ghost mr-1 py-1 text-xs" @click="open('kick', p)">Kick</button>
                <button class="btn-danger py-1 text-xs" @click="open('ban', p)"><Icon name="ban" :size="12" />Ban</button>
              </template>
            </td>
          </tr>
          <tr v-if="!live.players.length">
            <td colspan="4" class="py-8 text-center text-slate-500">{{ server.state === 'running' ? 'Nobody online right now' : 'Server is not running' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card flex flex-col lg:col-span-2">
      <div class="flex items-center gap-2 border-b border-surface-700 px-5 py-3">
        <h2 class="flex-1 font-semibold">Chat</h2>
        <input v-model="chatFilter" class="input max-w-[10rem] py-1 text-xs" placeholder="Search…" />
      </div>
      <div ref="chatBox" class="h-80 flex-1 space-y-1 overflow-y-auto px-5 py-3 text-sm">
        <div v-for="(c, i) in chat" :key="i">
          <span class="text-xs text-slate-600">{{ fmtTime(c.ts) }}</span>
          <span class="ml-1 font-semibold text-accent-400">{{ plainName(c.name) }}:</span>
          <span class="ml-1 text-slate-300">{{ c.message }}</span>
        </div>
        <p v-if="!chat.length" class="py-8 text-center text-slate-500">No chat messages since the panel started</p>
      </div>
      <form v-if="server.can_control" class="flex gap-2 border-t border-surface-700 p-2" @submit.prevent="say(sayText)">
        <input v-model="sayText" class="input py-1.5" placeholder="Message all players as Server…" :disabled="server.state !== 'running'" />
        <button class="btn-primary" :disabled="server.state !== 'running'"><Icon name="send" :size="14" /></button>
      </form>
    </div>

    <div class="card lg:col-span-5">
      <div class="border-b border-surface-700 px-5 py-3"><h2 class="font-semibold">Bans</h2></div>
      <form v-if="server.can_control" class="grid gap-2 border-b border-surface-700 p-4 md:grid-cols-5" @submit.prevent="addBan">
        <input v-model="manualBan.name" class="input" placeholder="Player name" />
        <input v-model="manualBan.beammp_id" class="input" placeholder="BeamMP ID (optional)" />
        <input v-model="manualBan.ip" class="input" placeholder="IP (optional)" />
        <input v-model="manualBan.reason" class="input" placeholder="Reason" />
        <button class="btn-danger" :disabled="!manualBan.name && !manualBan.beammp_id && !manualBan.ip"><Icon name="ban" :size="14" />Add ban</button>
      </form>
      <div class="overflow-x-auto">
        <table class="table">
          <thead><tr><th>Name</th><th>BeamMP ID</th><th>IP</th><th>Reason</th><th>By</th><th>When</th><th></th></tr></thead>
          <tbody>
            <tr v-for="b in bans" :key="b.id">
              <td class="font-medium">{{ b.name || '—' }}</td>
              <td class="font-mono text-xs text-slate-400">{{ b.beammp_id || '—' }}</td>
              <td class="text-xs text-slate-400">{{ b.ip || '—' }}</td>
              <td class="text-slate-300">{{ b.reason || '—' }}</td>
              <td class="text-slate-400">{{ b.created_by }}</td>
              <td class="whitespace-nowrap text-xs text-slate-500">{{ dateTime(b.created_at) }}</td>
              <td class="text-right"><button v-if="server.can_control" class="btn-ghost py-1 text-xs" @click="unban(b)">Unban</button></td>
            </tr>
            <tr v-if="!bans.length"><td colspan="7" class="py-6 text-center text-slate-500">No bans</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <Modal v-if="action" :title="`${action.kind === 'kick' ? 'Kick' : 'Ban'} ${plainName(action.player.name)}`" @close="action = null">
      <label class="label">Reason (shown to the player)</label>
      <input v-model="reason" class="input" maxlength="200" autofocus @keydown.enter="confirmAction" />
      <p v-if="action.kind === 'ban'" class="help">Bans by name{{ action.player.beammp ? ' and BeamMP ID' : '' }}. Online players are kicked immediately.</p>
      <template #footer>
        <button class="btn-ghost" @click="action = null">Cancel</button>
        <button class="btn-danger" @click="confirmAction">{{ action.kind === 'kick' ? 'Kick' : 'Ban' }}</button>
      </template>
    </Modal>
  </div>
</template>
