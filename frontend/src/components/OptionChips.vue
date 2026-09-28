<template>
  <div class="chips-field">
    <div class="chips">
      <button
        v-for="option in options"
        :key="option"
        type="button"
        class="chips__item"
        :class="{ 'is-active': isActive(option) }"
        @click="toggle(option)"
      >
        <el-icon v-if="isActive(option)" :size="12"><Check /></el-icon>
        {{ option }}
      </button>
    </div>

    <el-input
      v-if="typing"
      v-model="text"
      class="chips-field__input"
      :maxlength="maxlength"
      show-word-limit
      :placeholder="placeholder"
    />

    <p v-if="!modelValue && emptyHint" class="chips-field__hint">{{ emptyHint }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Check } from '@element-plus/icons-vue'

const SEPARATOR = '、'
const UNLIMITED = '不限'

const props = defineProps({
  modelValue: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  typing: { type: Boolean, default: false },
  emptyHint: { type: String, default: '' },
  placeholder: { type: String, default: '可多选，也可以自己补充' },
  maxlength: { type: Number, default: 200 },
})

const emit = defineEmits(['update:modelValue'])

// 选中态完全由文本推导，用户手改输入框后高亮依然一致
const parts = computed(() =>
  String(props.modelValue || '')
    .split(SEPARATOR)
    .map((item) => item.trim())
    .filter(Boolean)
)

const isActive = (option) => parts.value.includes(option)

const text = computed({
  get: () => props.modelValue || '',
  set: (value) => emit('update:modelValue', value),
})

const emitList = (list) => emit('update:modelValue', list.join(SEPARATOR))

const toggle = (option) => {
  if (option === UNLIMITED) {
    emitList(isActive(option) ? [] : [UNLIMITED])
    return
  }

  const next = parts.value.filter((item) => item !== UNLIMITED)
  const index = next.indexOf(option)
  if (index >= 0) {
    next.splice(index, 1)
  } else {
    next.push(option)
  }
  emitList(next)
}
</script>

<style scoped>
.chips-field {
  width: 100%;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.chips__item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 13px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-1);
  background: var(--card);
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.chips__item:hover {
  border-color: var(--brand-400);
  color: var(--brand-600);
}

.chips__item.is-active {
  background: var(--grad-brand);
  border-color: transparent;
  color: #fff;
  box-shadow: var(--shadow-sm);
}

.chips-field__hint {
  margin: 6px 0 0;
  color: var(--text-3);
  font-size: 12px;
}
</style>
