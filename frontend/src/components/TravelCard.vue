<template>
  <article class="tcard" @click="emit('open', task.task_id)">
    <div class="tcard__cover" :style="coverStyle">
      <el-tag
        class="tcard__status"
        :type="statusTagType(task.status)"
        effect="dark"
        size="small"
        round
      >
        {{ statusText(task.status) }}
      </el-tag>
      <span class="tcard__span">{{ days }} 天 {{ nights }} 晚</span>
    </div>

    <div class="tcard__body">
      <h3 class="tcard__title">{{ task.destination }}</h3>

      <p class="tcard__date">
        <el-icon :size="13"><Calendar /></el-icon>
        {{ formatDateRange(task.start_date, task.end_date) }}
      </p>

      <div class="tcard__chips">
        <span class="chip">
          <el-icon :size="12"><User /></el-icon>{{ peopleSummary(task) }}
        </span>
        <span class="chip">
          <el-icon :size="12"><Wallet /></el-icon>{{ formatMoney(task.total_budget) }}
        </span>
        <span v-if="task.hotel_preference" class="chip">
          <el-icon :size="12"><House /></el-icon>{{ task.hotel_preference }}
        </span>
        <span v-if="task.travel_style" class="chip">
          <el-icon :size="12"><Compass /></el-icon>{{ task.travel_style }}
        </span>
      </div>

      <div class="tcard__foot">
        <span class="tcard__more">
          查看详情<el-icon :size="12"><ArrowRight /></el-icon>
        </span>
        <el-tooltip content="删除该行程" placement="top">
          <el-button text type="danger" :icon="Delete" @click.stop="emit('delete', task)" />
        </el-tooltip>
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { ArrowRight, Calendar, Compass, Delete, House, User, Wallet } from '@element-plus/icons-vue'
import {
  calcDays,
  calcNights,
  coverGradient,
  coverImage,
  formatDateRange,
  formatMoney,
  peopleSummary,
  statusTagType,
  statusText,
} from '../utils/format'

const props = defineProps({
  task: { type: Object, required: true },
})

const emit = defineEmits(['open', 'delete'])

const days = computed(() => calcDays(props.task.start_date, props.task.end_date))
const nights = computed(() => calcNights(props.task.start_date, props.task.end_date))

const coverStyle = computed(() => {
  const image = coverImage(props.task.destination)
  return image
    ? { backgroundImage: `url(${image})` }
    : { background: coverGradient(props.task.destination) }
})
</script>

<style scoped>
.tcard {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--card);
  border: 1px solid var(--border-1);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.24s ease, box-shadow 0.24s ease, border-color 0.24s ease;
}

.tcard:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
  border-color: var(--brand-400);
}

.tcard__cover {
  position: relative;
  height: 116px;
  background-size: cover;
  background-position: center;
}

.tcard__cover::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.18) 0%, rgba(0, 0, 0, 0) 45%);
}

.tcard__status {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 1;
  backdrop-filter: blur(2px);
}

.tcard__span {
  position: absolute;
  left: 12px;
  bottom: 10px;
  z-index: 1;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.45);
}

.tcard__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 14px 16px 12px;
}

.tcard__title {
  font-size: 17px;
  letter-spacing: -0.2px;
}

.tcard__date {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 0;
  color: var(--text-3);
  font-size: 12.5px;
}

.tcard__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
}

.tcard__foot {
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--border-1);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tcard__more {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--brand-600);
  font-size: 12.5px;
  font-weight: 500;
}

.tcard:hover .tcard__more {
  gap: 6px;
}
</style>
