// Tracks background jobs (downloads, imports, template copies) started from this browser tab.
import { reactive } from 'vue'
import { api } from './api'
import { toast } from './store'

export const jobState = reactive({ list: [] })
const callbacks = new Map()
let timer = null

export function watchJob(job, { onDone, onError, quiet = false } = {}) {
  if (!job?.id) return
  const existing = jobState.list.find((j) => j.id === job.id)
  if (existing) Object.assign(existing, job)
  else jobState.list.unshift({ ...job, quiet })
  callbacks.set(job.id, { onDone, onError, quiet })
  if (!timer) timer = setInterval(poll, 800)
}

async function poll() {
  const running = jobState.list.filter((j) => j.status === 'running')
  if (!running.length) {
    clearInterval(timer)
    timer = null
    return
  }
  await Promise.all(
    running.map(async (j) => {
      let fresh
      try {
        fresh = await api.get(`/api/jobs/${j.id}`)
      } catch {
        return
      }
      Object.assign(j, fresh)
      if (fresh.status === 'running') return
      const cb = callbacks.get(j.id) || {}
      callbacks.delete(j.id)
      if (fresh.status === 'done') {
        if (!cb.quiet) toast(`${fresh.label}: done`, 'success')
        cb.onDone?.(fresh.result, fresh)
      } else {
        toast(`${fresh.label} failed: ${fresh.error}`, 'error')
        cb.onError?.(fresh)
      }
      setTimeout(() => dismiss(j.id), fresh.status === 'done' ? 4000 : 15000)
    }),
  )
}

export function dismiss(id) {
  const i = jobState.list.findIndex((j) => j.id === id)
  if (i >= 0) jobState.list.splice(i, 1)
}
