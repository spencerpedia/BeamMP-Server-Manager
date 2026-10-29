<script setup>
import { ref } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({ accept: String, multiple: Boolean, hint: String, progress: Number, disabled: Boolean })
const emit = defineEmits(['files'])
const over = ref(false)
const input = ref(null)

function drop(e) {
  over.value = false
  if (props.disabled) return
  const files = [...e.dataTransfer.files]
  if (files.length) emit('files', props.multiple ? files : files.slice(0, 1))
}
function pick(e) {
  const files = [...e.target.files]
  if (files.length) emit('files', files)
  e.target.value = ''
}
</script>

<template>
  <div
    class="relative flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition"
    :class="[over ? 'border-accent-500 bg-accent-500/5' : 'border-surface-600 hover:border-surface-600 hover:bg-surface-800/50', disabled && 'pointer-events-none opacity-50']"
    @dragover.prevent="over = true"
    @dragleave="over = false"
    @drop.prevent="drop"
    @click="input.click()"
  >
    <Icon name="upload" :size="28" class="mb-2 text-slate-400" />
    <div class="text-sm text-slate-300"><span class="font-semibold text-accent-400">Click to upload</span> or drag and drop</div>
    <div v-if="hint" class="mt-1 text-xs text-slate-500">{{ hint }}</div>
    <input ref="input" type="file" class="hidden" :accept="accept" :multiple="multiple" @change="pick" />
    <div v-if="progress != null" class="absolute inset-x-0 bottom-0 h-1 overflow-hidden rounded-b-xl bg-surface-700">
      <div class="h-full bg-accent-500 transition-all" :style="{ width: `${Math.round(progress * 100)}%` }" />
    </div>
  </div>
</template>
