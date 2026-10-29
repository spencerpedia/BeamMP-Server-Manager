// Thin fetch wrapper: JSON in/out, cookie auth, throws Error(detail) on failure.
export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function request(method, url, body, { raw = false } = {}) {
  const opts = { method, credentials: 'same-origin', headers: {} }
  if (body instanceof FormData) {
    opts.body = body
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(url, opts)
  if (res.status === 401 && !url.startsWith('/api/auth/')) {
    window.dispatchEvent(new CustomEvent('bmsm:unauthorized'))
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {}
    throw new ApiError(res.status, detail)
  }
  if (raw) return res
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

export const api = {
  get: (url) => request('GET', url),
  post: (url, body) => request('POST', url, body),
  put: (url, body) => request('PUT', url, body),
  patch: (url, body) => request('PATCH', url, body),
  del: (url) => request('DELETE', url),
}

// Uploads with progress (fetch can't report upload progress).
export function upload(url, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
    xhr.onload = () => {
      let data = null
      try { data = JSON.parse(xhr.responseText) } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(data)
      else reject(new ApiError(xhr.status, data?.detail || xhr.statusText))
    }
    xhr.onerror = () => reject(new ApiError(0, 'Network error'))
    xhr.send(formData)
  })
}

export function socket(path, onMessage, onStatus) {
  // Reconnecting WebSocket. Returns a close() function.
  let ws, timer, closed = false
  const connect = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}${path}`)
    ws.onopen = () => onStatus?.(true)
    ws.onmessage = (e) => onMessage(JSON.parse(e.data))
    ws.onclose = (e) => {
      onStatus?.(false)
      if (!closed && e.code !== 4401 && e.code !== 4403) timer = setTimeout(connect, 2000)
    }
  }
  connect()
  return () => {
    closed = true
    clearTimeout(timer)
    ws?.close()
  }
}
