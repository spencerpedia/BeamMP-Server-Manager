// Shared live server list: REST snapshot + dashboard WebSocket for state, stats and players.
import { reactive } from 'vue'
import { api, socket } from './api'

export const servers = reactive({ list: [], loaded: false, connected: false })
let closeSocket = null

export async function refreshServers() {
  servers.list = await api.get('/api/servers')
  servers.loaded = true
}

export function findServer(id) {
  return servers.list.find((s) => s.id === id)
}

function apply(msg) {
  const s = findServer(msg.server_id)
  if (!s) {
    if (msg.type === 'state') refreshServers().catch(() => {})
    return
  }
  if (msg.type === 'state') {
    s.state = msg.state
    if (msg.version) s.version_running = msg.version
    if (msg.state !== 'running') s.stats = null
  } else if (msg.type === 'stats') {
    s.stats = { cpu: msg.cpu, mem: msg.mem, players: msg.players, ts: msg.ts }
    s.uptime = msg.uptime
  } else if (msg.type === 'players') {
    s.players = msg.players
  }
}

export function connectServers() {
  if (closeSocket) return
  closeSocket = socket('/ws/dashboard', apply, (ok) => {
    servers.connected = ok
    if (ok) refreshServers().catch(() => {})
  })
}

export function disconnectServers() {
  closeSocket?.()
  closeSocket = null
  servers.list = []
  servers.loaded = false
}
