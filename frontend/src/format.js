export function bytes(n) {
  if (n == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${units[i]}`
}

export function duration(sec) {
  if (!sec) return '—'
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60)
  if (d) return `${d}d ${h}h`
  if (h) return `${h}h ${m}m`
  return `${m}m ${sec % 60}s`
}

export function dateTime(v) {
  if (!v) return '—'
  const d = typeof v === 'number' ? new Date(v * 1000) : new Date(v)
  return d.toLocaleString()
}

export function timeAgo(v) {
  if (!v) return 'never'
  const d = typeof v === 'number' ? new Date(v * 1000) : new Date(v)
  const s = Math.round((Date.now() - d.getTime()) / 1000)
  if (s < -86400) return `in ${Math.round(-s / 86400)} d`
  if (s < -5400) return `in ${Math.round(-s / 3600)} h`
  if (s < -60) return `in ${Math.round(-s / 60)} min`
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return d.toLocaleDateString()
}

// Strip BeamMP ^-colour codes for plain display.
export const plainName = (s) => (s || '').replace(/\^[0-9a-fk-or]/gi, '')

export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
