<template>
  <div class="budget">
    <div class="budget__head">
      <span class="muted">预估总花费</span>
      <span class="budget__sum num">{{ formatMoney(cost) }}</span>
    </div>

    <template v-if="hasBudget">
      <el-progress
        :percentage="percent"
        :show-text="false"
        :stroke-width="8"
        :color="over ? 'var(--danger)' : 'var(--brand-500)'"
      />
      <p class="budget__hint" :class="over ? 'is-over' : 'is-ok'">
        <el-icon :size="14">
          <WarningFilled v-if="over" />
          <CircleCheckFilled v-else />
        </el-icon>
        {{ over ? `超出预算 ${formatMoney(diff)}` : `预算内，结余 ${formatMoney(-diff)}` }}
      </p>
    </template>

    <p v-else class="budget__hint muted">该行程未设置预算，不做超支判断</p>

    <p v-if="basis" class="budget__basis">{{ basis }}</p>

    <p v-if="upsell" class="budget__upsell">
      <el-icon :size="13"><InfoFilled /></el-icon>
      <span>{{ upsell }}</span>
    </p>

    <p v-if="breakdownText" class="budget__breakdown num">{{ breakdownText }}</p>

    <div class="budget__foot">
      <span v-if="peopleNum">人均 {{ formatMoney(perPerson) }}</span>
      <span v-if="days">{{ days }} 天</span>
      <span v-if="hasBudget">预算 {{ formatMoney(budget) }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CircleCheckFilled, InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import { formatMoney } from '../utils/format'

const BREAKDOWN_LABELS = { hotel: '住宿', food: '餐饮', transport: '交通', ticket: '门票' }

const props = defineProps({
  totalCost: { type: [Number, String], default: null },
  totalBudget: { type: [Number, String], default: null },
  days: { type: Number, default: 0 },
  peopleNum: { type: Number, default: 0 },
  budget: { type: Object, default: null },
})

const basis = computed(() => props.budget?.basis || '')
const upsell = computed(() => props.budget?.upsell || '')

const breakdownText = computed(() => {
  const items = props.budget?.breakdown
  if (!items) return ''
  return Object.entries(BREAKDOWN_LABELS)
    .filter(([key]) => items[key] !== undefined && items[key] !== null)
    .map(([key, label]) => `${label} ${formatMoney(items[key])}`)
    .join(' · ')
})

const cost = computed(() => Number(props.totalCost) || 0)
const budget = computed(() => Number(props.totalBudget) || 0)
const hasBudget = computed(() => budget.value > 0)
const over = computed(() => hasBudget.value && cost.value > budget.value)
const diff = computed(() => cost.value - budget.value)
const percent = computed(() =>
  hasBudget.value ? Math.min(Math.round((cost.value / budget.value) * 100), 100) : 0
)
const perPerson = computed(() => (props.peopleNum > 0 ? cost.value / props.peopleNum : 0))
</script>

<style scoped>
.budget {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.budget__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}

.budget__sum {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-1);
  letter-spacing: -0.3px;
}

.budget__hint {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 0;
  font-size: 12.5px;
}

.budget__hint.is-over {
  color: var(--danger);
}

.budget__hint.is-ok {
  color: var(--success);
}

.budget__basis {
  margin: 0;
  color: var(--text-3);
  font-size: 11.5px;
  line-height: 1.6;
}

.budget__upsell {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  margin: 0;
  padding: 7px 10px;
  border-radius: var(--radius-sm);
  background: var(--grad-brand-soft);
  color: var(--brand-600);
  font-size: 12px;
  line-height: 1.55;
}

.budget__upsell .el-icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.budget__breakdown {
  margin: 0;
  color: var(--text-3);
  font-size: 11.5px;
}

.budget__foot {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-1);
  color: var(--text-3);
  font-size: 12.5px;
}
</style>
