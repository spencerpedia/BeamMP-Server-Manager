<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip } from 'chart.js'

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip)

const props = defineProps({
  labels: Array,
  values: Array,
  color: { type: String, default: '#f97316' },
  format: { type: Function, default: (v) => v },
  max: Number,
})
const canvas = ref(null)
let chart

onMounted(() => {
  chart = new Chart(canvas.value, {
    type: 'line',
    data: {
      labels: props.labels,
      datasets: [{ data: props.values, borderColor: props.color, backgroundColor: props.color + '22', fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2 }],
    },
    options: {
      animation: false,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: 'index' },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => props.format(c.parsed.y) } } },
      scales: {
        x: { ticks: { color: '#64748b', maxTicksLimit: 6, maxRotation: 0 }, grid: { color: '#1e293b' } },
        y: { beginAtZero: true, suggestedMax: props.max, ticks: { color: '#64748b', callback: (v) => props.format(v) }, grid: { color: '#1e293b' } },
      },
    },
  })
})

watch(
  () => [props.labels, props.values],
  () => {
    if (!chart) return
    chart.data.labels = props.labels
    chart.data.datasets[0].data = props.values
    chart.update('none')
  },
  { deep: true },
)
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div class="relative h-56"><canvas ref="canvas" /></div>
</template>
