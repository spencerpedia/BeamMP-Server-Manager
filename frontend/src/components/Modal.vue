<script setup>
defineProps({ title: String, wide: Boolean, xl: Boolean })
const emit = defineEmits(['close'])
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/60 p-4 pt-[6vh]" @mousedown.self="emit('close')">
      <div class="card w-full shadow-2xl" :class="xl ? 'max-w-6xl' : wide ? 'max-w-2xl' : 'max-w-md'">
        <div class="flex items-center justify-between border-b border-surface-700 px-5 py-3">
          <h2 class="font-semibold text-slate-100">{{ title }}</h2>
          <button class="text-slate-400 hover:text-slate-100" @click="emit('close')" aria-label="Close">✕</button>
        </div>
        <div class="p-5" :class="{ 'max-h-[75vh] overflow-y-auto': xl }"><slot /></div>
        <div v-if="$slots.footer" class="flex justify-end gap-2 border-t border-surface-700 px-5 py-3"><slot name="footer" /></div>
      </div>
    </div>
  </Teleport>
</template>
