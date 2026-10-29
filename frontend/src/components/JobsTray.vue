<script setup>
import { jobState, dismiss } from '../jobs'
</script>

<template>
  <div v-if="jobState.list.length" class="fixed bottom-4 left-4 z-40 flex w-80 flex-col gap-2 md:left-[17rem]">
    <div v-for="j in jobState.list" :key="j.id" class="card px-4 py-3 text-sm shadow-xl">
      <div class="flex items-start gap-2">
        <div class="min-w-0 flex-1">
          <div class="truncate font-medium text-slate-100">{{ j.label }}</div>
          <div class="truncate text-xs" :class="j.status === 'error' ? 'text-red-400' : 'text-slate-400'">
            {{ j.status === 'error' ? j.error : j.status === 'done' ? 'Done' : j.message || 'Working…' }}
          </div>
        </div>
        <button v-if="j.status !== 'running'" class="text-slate-500 hover:text-slate-200" @click="dismiss(j.id)">✕</button>
      </div>
      <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-700">
        <div
          class="h-full rounded-full transition-all"
          :class="[j.status === 'error' ? 'bg-red-500' : j.status === 'done' ? 'bg-emerald-500' : 'bg-accent-500', j.progress == null && j.status === 'running' ? 'w-1/3 animate-pulse' : '']"
          :style="j.progress != null || j.status !== 'running' ? { width: `${Math.round((j.status === 'running' ? j.progress : 1) * 100)}%` } : {}"
        />
      </div>
    </div>
  </div>
</template>
