<template>
  <span v-if="weather" class="wtag">
    <el-icon :size="14"><component :is="weatherIcon(weather)" /></el-icon>
    <span>{{ weather }}</span>
    <span v-if="temp" class="wtag__temp num">{{ temp }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { weatherIcon } from '../utils/format'

const props = defineProps({
  weather: { type: String, default: '' },
  tempMin: { type: [Number, String], default: null },
  tempMax: { type: [Number, String], default: null },
})

const temp = computed(() =>
  props.tempMin === null || props.tempMin === '' || props.tempMax === null || props.tempMax === ''
    ? ''
    : `${props.tempMin}~${props.tempMax}℃`
)
</script>

<style scoped>
.wtag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--grad-brand-soft);
  color: var(--brand-600);
  font-size: 12px;
  white-space: nowrap;
}

.wtag__temp {
  color: var(--text-2);
}
</style>
