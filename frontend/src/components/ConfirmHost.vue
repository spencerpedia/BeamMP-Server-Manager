<script setup>
import Modal from './Modal.vue'
import { confirmState, closeConfirm } from './confirm'
</script>

<template>
  <Modal v-if="confirmState.open" :title="confirmState.title" @close="closeConfirm(false)">
    <p class="text-sm text-slate-300 whitespace-pre-line">{{ confirmState.message }}</p>
    <template #footer>
      <button class="btn-ghost" @click="closeConfirm(false)">Cancel</button>
      <button :class="confirmState.danger ? 'btn-danger' : 'btn-primary'" @click="closeConfirm(true)">{{ confirmState.confirmText }}</button>
    </template>
  </Modal>
</template>
