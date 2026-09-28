<template>
  <div class="wstrip">
    <div v-if="days.length" class="wstrip__row">
      <div v-for="day in days" :key="day.date" class="wstrip__cell">
        <span class="wstrip__date num">{{ shortDate(day.date) }}</span>
        <el-icon class="wstrip__icon" :size="20">
          <component :is="weatherIcon(day.weather)" />
        </el-icon>
        <span class="wstrip__text">{{ day.weather || '—' }}</span>
        <span class="wstrip__temp num">{{ tempText(day) }}</span>
        <span class="wstrip__precip">{{ precipText(day) }}</span>
      </div>
    </div>

    <p v-else-if="summary" class="wstrip__summary">{{ summary }}</p>

    <p v-if="days.length && advice" class="wstrip__advice">
      <el-icon :size="13"><InfoFilled /></el-icon>
      <span>{{ advice }}</span>
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { weatherIcon } from '../utils/format'

const props = defineProps({
  forecast: { type: Array, default: () => [] },
  summary: { type: String, default: '' },
  advice: { type: String, default: '' },
})

const days = computed(() => (props.forecast || []).filter((day) => day && day.date))

const shortDate = (date) => String(date || '').slice(5)

const tempText = (day) =>
  day.temp_min === null || day.temp_min === undefined || day.temp_max === null || day.temp_max === undefined
    ? '—'
    : `${day.temp_min}~${day.temp_max}℃`

const precipText = (day) => {
  const value = Number(day.precip)
  return value > 0 ? `降水 ${value}mm` : ''
}
</script>

<style scoped>
.wstrip {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wstrip__row {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.wstrip__cell {
  flex: 1 0 auto;
  min-width: 88px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 10px 8px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
}

.wstrip__date {
  font-size: 11.5px;
  color: var(--text-3);
}

.wstrip__icon {
  color: var(--brand-500);
}

.wstrip__text {
  font-size: 13px;
  color: var(--text-1);
}

.wstrip__temp {
  font-size: 12.5px;
  color: var(--text-2);
}

.wstrip__precip {
  min-height: 14px;
  font-size: 11px;
  color: var(--text-3);
}

.wstrip__summary {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-2);
}

.wstrip__advice {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  margin: 0;
  padding: 7px 10px;
  border-radius: var(--radius-sm);
  background: var(--grad-brand-soft);
  color: var(--brand-600);
  font-size: 12px;
  line-height: 1.6;
}

.wstrip__advice .el-icon {
  flex-shrink: 0;
  margin-top: 2px;
}
</style>
