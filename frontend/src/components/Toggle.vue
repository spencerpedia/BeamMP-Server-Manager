<script setup>
const model = defineModel({ type: Boolean })
defineProps({ disabled: Boolean })
</script>

<template>
  <button
    type="button"
    role="switch"
    :aria-checked="model"
    :disabled="disabled"
    class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition disabled:opacity-50"
    :class="model ? 'bg-accent-500' : 'bg-surface-600'"
    @click="model = !model"
  >
    <span class="inline-block h-4 w-4 rounded-full bg-white shadow transition" :class="model ? 'translate-x-[18px]' : 'translate-x-0.5'" />
  </button>
</template>
