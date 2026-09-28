<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">创建旅行计划</h2>
        <p class="page-sub">填写得越具体，生成的行程越贴合你的预期</p>
      </div>
      <el-button text :icon="ArrowLeft" @click="router.push('/travel/list')">返回列表</el-button>
    </div>

    <el-row :gutter="20">
      <el-col :xs="24" :lg="16">
        <el-card class="form-card">
          <el-form
            ref="formRef"
            :model="form"
            :rules="rules"
            label-width="92px"
            label-position="left"
          >
            <div class="section-title">基本信息</div>

            <el-form-item label="目的地" prop="destination">
              <el-input v-model="form.destination" placeholder="如：北京、上海、广州" clearable />
            </el-form-item>

            <el-form-item label="出行日期" prop="date_range">
              <el-date-picker
                v-model="form.date_range"
                type="daterange"
                value-format="YYYY-MM-DD"
                range-separator="→"
                start-placeholder="出发日期"
                end-placeholder="返程日期"
                :disabled-date="disabledDate"
                style="width: 100%"
              />
            </el-form-item>

            <el-form-item label="出行人数" prop="people_num">
              <div class="people">
                <div class="people__item">
                  <el-input-number v-model="form.people_num" :min="1" :max="50" />
                  <span class="unit">人</span>
                </div>
                <span class="people__split">其中</span>
                <div class="people__item">
                  <el-input-number
                    v-model="form.male_num"
                    class="people__mini"
                    :min="0"
                    :max="50"
                    :controls="false"
                  />
                  <span class="unit">男</span>
                </div>
                <div class="people__item">
                  <el-input-number
                    v-model="form.female_num"
                    class="people__mini"
                    :min="0"
                    :max="50"
                    :controls="false"
                  />
                  <span class="unit">女</span>
                </div>
              </div>
              <p v-if="peopleWarning" class="field-warning">{{ peopleWarning }}</p>
            </el-form-item>

            <el-form-item label="总预算" prop="total_budget">
              <el-input-number v-model="form.total_budget" :min="0" :step="500" />
              <span class="unit">元（留空表示不限制）</span>
            </el-form-item>

            <div class="section-title">偏好设置</div>

            <el-form-item label="住宿偏好">
              <OptionChips
                v-model="form.hotel_preference"
                :options="HOTEL_OPTIONS"
                empty-hint="不选表示不需要安排住宿"
              />
            </el-form-item>

            <el-form-item label="游玩风格">
              <OptionChips v-model="form.travel_style" :options="STYLE_OPTIONS" typing />
            </el-form-item>

            <el-form-item label="交通方式">
              <OptionChips v-model="form.traffic_type" :options="TRAFFIC_OPTIONS" typing />
            </el-form-item>

            <div class="section-title">额外需求</div>

            <el-form-item label="备注">
              <el-input
                v-model="form.extra_require"
                type="textarea"
                :rows="3"
                maxlength="300"
                show-word-limit
                placeholder="如：希望安排一天购物、对海鲜过敏、每天不超过 2 万步"
              />
            </el-form-item>

            <el-form-item label-width="0">
              <el-button
                type="primary"
                class="submit"
                :icon="MagicStick"
                :loading="submitting"
                @click="submit"
              >
                {{ submitting ? '正在提交…' : '生成行程' }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8">
        <el-card class="summary">
          <div class="summary__cover" :style="coverStyle">
            <span>{{ form.destination || '待定目的地' }}</span>
          </div>

          <div class="section-title">行程概要</div>

          <ul class="summary__list">
            <li>
              <span class="muted">日期</span>
              <strong>{{ dateLabel }}</strong>
            </li>
            <li>
              <span class="muted">天数</span>
              <strong>{{ days ? `${days} 天 ${nights} 晚` : '—' }}</strong>
            </li>
            <li>
              <span class="muted">人数</span>
              <strong>{{ peopleSummary(form) }}</strong>
            </li>
            <li>
              <span class="muted">总预算</span>
              <strong>{{ budgetLabel }}</strong>
            </li>
            <li v-if="perPerson > 0">
              <span class="muted">人均预算</span>
              <strong>{{ formatMoney(perPerson) }}</strong>
            </li>
          </ul>

          <div class="summary__chips">
            <span v-if="form.hotel_preference" class="chip">{{ form.hotel_preference }}</span>
            <span v-else class="chip chip--muted">不安排住宿</span>
            <span v-if="form.travel_style" class="chip">{{ form.travel_style }}</span>
            <span v-if="form.traffic_type" class="chip">{{ form.traffic_type }}</span>
          </div>

          <p class="summary__note">
            <el-icon :size="13"><Timer /></el-icon>
            生成需要 1–3 分钟，提交后可离开页面，后台继续生成
          </p>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, MagicStick, Timer } from '@element-plus/icons-vue'
import { createTask, generatePlan } from '../api/travel'
import OptionChips from '../components/OptionChips.vue'
import {
  calcDays,
  calcNights,
  coverGradient,
  coverImage,
  formatDateRange,
  formatMoney,
  peopleSummary,
} from '../utils/format'

const HOTEL_OPTIONS = ['不限', '经济型酒店', '中档型酒店', '豪华型酒店', '民宿/客栈', '青年旅舍']
const STYLE_OPTIONS = [
  '不限',
  '自然风光',
  '历史文化',
  '美食探店',
  '亲子活动',
  '休闲度假',
  '艺术展览',
  '购物逛街',
]
const TRAFFIC_OPTIONS = ['不限', '公共交通', '自驾', '网约车', '骑行', '步行']

const router = useRouter()
const formRef = ref(null)
const submitting = ref(false)

const form = ref({
  destination: '',
  date_range: [],
  people_num: 2,
  male_num: null,
  female_num: null,
  total_budget: 5000,
  hotel_preference: '',
  travel_style: '',
  traffic_type: '',
  extra_require: '',
})

const rules = {
  destination: [
    { required: true, message: '请填写目的地', trigger: 'blur' },
    { max: 100, message: '目的地不超过 100 个字符', trigger: 'blur' },
  ],
  date_range: [
    {
      trigger: 'change',
      validator: (_rule, value, callback) =>
        Array.isArray(value) && value.length === 2
          ? callback()
          : callback(new Error('请选择完整的出行日期')),
    },
  ],
  people_num: [{ required: true, message: '请填写出行人数', trigger: 'change' }],
}

const days = computed(() => {
  const range = form.value.date_range || []
  return range.length === 2 ? calcDays(range[0], range[1]) : 0
})
const nights = computed(() => calcNights(...(form.value.date_range || [])))

const dateLabel = computed(() => {
  const range = form.value.date_range || []
  return range.length === 2 ? formatDateRange(range[0], range[1]) : '待定'
})

const budgetLabel = computed(() =>
  form.value.total_budget ? formatMoney(form.value.total_budget) : '不限'
)

const perPerson = computed(() =>
  form.value.total_budget > 0 ? Math.round(form.value.total_budget / Math.max(form.value.people_num, 1)) : 0
)

// 只提示不拦截：男女是否填、是否与总人数对齐都不影响提交
const peopleWarning = computed(() => {
  const male = Number(form.value.male_num) || 0
  const female = Number(form.value.female_num) || 0
  const total = Number(form.value.people_num) || 0
  return male + female > total ? `男女合计 ${male + female} 人，超过总人数 ${total} 人` : ''
})

const coverStyle = computed(() => {
  const image = coverImage(form.value.destination)
  return image
    ? { backgroundImage: `url(${image})` }
    : { background: coverGradient(form.value.destination || '旅行') }
})

// 只能选今天及以后。这里不能减一天：那会把「昨天」也放进可选范围
const disabledDate = (date) => date.getTime() < new Date().setHours(0, 0, 0, 0)

const submit = async () => {
  if (submitting.value) return
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const [start, end] = form.value.date_range
    const { date_range, ...rest } = form.value
    const task = await createTask({ ...rest, start_date: start, end_date: end })

    try {
      await generatePlan(task.task_id)
      ElMessage.success('行程已创建，正在后台生成…')
    } catch {
      ElMessage.warning('行程已创建，但生成请求失败，可在详情页重试')
    }

    router.push(`/travel/detail/${task.task_id}`)
  } catch {
    // 创建失败提示由拦截器处理，停留在当前页让用户修改
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.form-card {
  border-radius: var(--radius-md);
}

.section-title:not(:first-child) {
  margin-top: 22px;
}

.unit {
  margin-left: 10px;
  color: var(--text-3);
  font-size: 12.5px;
}

.people {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.people__item {
  display: flex;
  align-items: center;
}

.people__mini {
  width: 72px;
}

.people__split {
  color: var(--text-3);
  font-size: 12.5px;
}

.field-warning {
  margin: 6px 0 0;
  color: var(--warning);
  font-size: 12px;
}

.chip--muted {
  color: var(--text-3);
  border-style: dashed;
}

.submit {
  width: 100%;
  height: 44px;
  font-size: 15px;
  background: var(--grad-brand);
  border: none;
  box-shadow: var(--shadow-md);
}

.summary {
  position: sticky;
  top: calc(var(--header-h) + 26px);
}

.summary__cover {
  height: 104px;
  margin: -20px -20px 18px;
  border-radius: var(--radius-md) var(--radius-md) 0 0;
  display: flex;
  align-items: flex-end;
  padding: 12px 16px;
  background-size: cover;
  background-position: center;
  color: #fff;
  font-size: 17px;
  font-weight: 600;
  text-shadow: 0 1px 8px rgba(0, 0, 0, 0.45);
}

.summary__list {
  list-style: none;
  margin: 0 0 14px;
  padding: 0;
  display: grid;
  gap: 9px;
}

.summary__list li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
}

.summary__list strong {
  color: var(--text-1);
  font-weight: 600;
}

.summary__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 14px;
  border-top: 1px dashed var(--border-1);
}

.summary__note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 16px 0 0;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
  color: var(--text-3);
  font-size: 12px;
}

@media (max-width: 1199px) {
  .summary {
    position: static;
    margin-top: 18px;
  }
}
</style>
