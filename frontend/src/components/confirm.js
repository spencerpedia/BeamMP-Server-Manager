import { reactive } from 'vue'

export const confirmState = reactive({ open: false, title: '', message: '', danger: false, confirmText: 'Confirm', resolve: null })

export function confirmDialog(message, { title = 'Are you sure?', danger = false, confirmText = 'Confirm' } = {}) {
  return new Promise((resolve) => Object.assign(confirmState, { open: true, title, message, danger, confirmText, resolve }))
}

export function closeConfirm(result) {
  confirmState.open = false
  confirmState.resolve?.(result)
}
