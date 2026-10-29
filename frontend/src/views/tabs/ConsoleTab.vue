<script setup>
import { inject, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { api } from '../../api'
import { toastError } from '../../store'
import Icon from '../../components/Icon.vue'

const server = inject('server')
const live = inject('live')
const onLog = inject('onLog')
const el = ref(null)
const command = ref('')
const history = []
let historyPos = -1
let term, fit, unsub, resizeObs

// Colour BeamMP's [LEVEL] tags since the server doesn't emit ANSI colours when piped.
const LEVEL_COLORS = { '[INFO]': '32', '[WARN]': '33', '[ERROR]': '31', '[DEBUG]': '90', '[LUA]': '35', '[CHAT]': '36' }
function colorize(line) {
  return line.replace(/^(\[[^\]]+\]) (\[[A-Z]+\])/, (_, ts, lvl) => `\x1b[90m${ts}\x1b[0m \x1b[${LEVEL_COLORS[lvl] || '37'}m${lvl}\x1b[0m`)
}

onMounted(async () => {
  term = new Terminal({
    convertEol: true,
    disableStdin: true,
    fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace',
    fontSize: 13,
    scrollback: 5000,
    theme: { background: '#0b0f17', foreground: '#cbd5e1', cursor: '#0b0f17', selectionBackground: '#2e3a54' },
  })
  fit = new FitAddon()
  term.loadAddon(fit)
  term.open(el.value)
  await nextTick()
  fit.fit()
  live.log.forEach((l) => term.writeln(colorize(l)))
  unsub = onLog((line, all) => {
    if (all) {
      term.clear()
      term.reset()
      all.forEach((l) => term.writeln(colorize(l)))
    } else {
      term.writeln(colorize(line))
    }
  })
  resizeObs = new ResizeObserver(() => fit.fit())
  resizeObs.observe(el.value)
})

onBeforeUnmount(() => {
  unsub?.()
  resizeObs?.disconnect()
  term?.dispose()
})

async function send() {
  const cmd = command.value.trim()
  if (!cmd) return
  try {
    await api.post(`/api/servers/${server.value.id}/console`, { command: cmd })
    history.unshift(cmd)
    historyPos = -1
    command.value = ''
  } catch (e) {
    toastError(e)
  }
}

function navHistory(dir) {
  if (!history.length) return
  historyPos = Math.max(-1, Math.min(history.length - 1, historyPos + dir))
  command.value = historyPos === -1 ? '' : history[historyPos]
}

const quick = [
  ['status', 'status'],
  ['list', 'list'],
  ['help', 'help'],
]
</script>

<template>
  <div class="card overflow-hidden">
    <div class="flex items-center gap-2 border-b border-surface-700 px-4 py-2 text-xs text-slate-400">
      <span class="h-2 w-2 rounded-full" :class="live.connected ? 'bg-emerald-400' : 'bg-red-400'" />
      {{ live.connected ? 'Live' : 'Disconnected' }}
      <span class="flex-1" />
      <template v-if="server.can_control">
        <button v-for="[label, cmd] in quick" :key="cmd" class="rounded px-2 py-0.5 hover:bg-surface-700 hover:text-slate-100" @click="command = cmd; send()">{{ label }}</button>
      </template>
    </div>
    <div ref="el" class="h-[60vh] min-h-[320px] bg-surface-950 p-2" />
    <form v-if="server.can_control" class="flex items-center gap-2 border-t border-surface-700 bg-surface-900 p-2" @submit.prevent="send">
      <span class="pl-2 font-mono text-accent-400">&gt;</span>
      <input
        v-model="command"
        class="flex-1 bg-transparent font-mono text-sm text-slate-100 outline-none placeholder:text-slate-600"
        placeholder="Type a console command (e.g. say Hello!, kick <name>, status)"
        :disabled="server.state !== 'running'"
        @keydown.up.prevent="navHistory(1)"
        @keydown.down.prevent="navHistory(-1)"
      />
      <button class="btn-primary" :disabled="server.state !== 'running' || !command.trim()"><Icon name="send" :size="14" />Send</button>
    </form>
  </div>
</template>
