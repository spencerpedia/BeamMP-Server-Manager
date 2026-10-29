import { reactive } from 'vue'
import { api } from './api'

export const store = reactive({
  user: null,
  loaded: false,
  toasts: [],
})

let toastId = 0
export function toast(message, kind = 'info') {
  const id = ++toastId
  store.toasts.push({ id, message, kind })
  setTimeout(() => {
    const i = store.toasts.findIndex((t) => t.id === id)
    if (i >= 0) store.toasts.splice(i, 1)
  }, kind === 'error' ? 7000 : 3500)
}

export function toastError(e) {
  toast(e?.message || String(e), 'error')
}

export async function loadUser() {
  try {
    store.user = await api.get('/api/auth/me')
  } catch {
    store.user = null
  }
  store.loaded = true
  return store.user
}

export const isAdmin = () => store.user?.role === 'admin'
