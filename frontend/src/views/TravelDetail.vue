<template>
  <div class="page">
    <el-card v-if="loading">
      <el-skeleton :rows="7" animated />
    </el-card>

    <el-empty v-else-if="!task" :image-size="120" description="行程不存在或已被删除">
      <el-button type="primary" @click="router.push('/travel/list')">返回列表</el-button>
    </el-empty>

    <template v-else>
      <section class="hero" :style="heroStyle">
        <button class="hero__back" type="button" @click="router.push('/travel/list')">
          <el-icon><ArrowLeft /></el-icon>返回列表
        </button>

        <h2 class="hero__title">{{ task.destination }}</h2>

        <p class="hero__meta">
          <el-icon :size="14"><Calendar /></el-icon>
          {{ formatDateRange(task.start_date, task.end_date) }}
          <span class="hero__dot">·</span>{{ spanDays }} 天 {{ spanNights }} 晚
          <span class="hero__dot">·</span>{{ peopleSummary(task) }}
        </p>

        <div class="hero__tags">
          <el-tag :type="statusTagType(task.status)" effect="dark" round>
            {{ statusText(task.status) }}
          </el-tag>
          <span v-if="task.hotel_preference" class="hero__chip">{{ task.hotel_preference }}</span>
          <span v-if="task.travel_style" class="hero__chip">{{ task.travel_style }}</span>
          <span v-if="task.traffic_type" class="hero__chip">{{ task.traffic_type }}</span>
          <span v-if="task.total_budget" class="hero__chip">
            预算 {{ formatMoney(task.total_budget) }}
          </span>
        </div>
      </section>

      <el-card v-if="isRunning" class="state-card">
        <div class="state">
          <el-icon class="state__icon is-spin" :size="30"><Loading /></el-icon>
          <h3>{{ task.status === 'pending' ? '等待开始生成' : 'AI 正在规划行程' }}</h3>
          <p>
            正在联网查攻略、检索知识库、核算预算并生成逐日安排，通常需要 1–3 分钟。
          </p>
          <div class="state__steps">
            <span class="chip">联网搜索</span>
            <span class="chip">知识库检索</span>
            <span class="chip">预算核算</span>
            <span class="chip">逐日行程生成</span>
          </div>
          <el-button :icon="Refresh" :loading="refreshing" @click="refresh">立即刷新状态</el-button>
          <small class="muted">页面每 3 秒自动检查一次，可以先去忙别的</small>
        </div>
      </el-card>

      <el-card v-else-if="task.status === 'failed'" class="state-card">
        <el-result
          icon="error"
          title="行程生成失败"
          sub-title="常见原因是模型调用超时或额度不足，可以重试一次"
        >
          <template #extra>
            <el-button type="primary" :icon="RefreshRight" :loading="regenerating" @click="regenerate">
              重新生成
            </el-button>
            <el-button @click="router.push('/travel/list')">返回列表</el-button>
          </template>
        </el-result>
      </el-card>

      <template v-else-if="plan">
        <el-row :gutter="18" class="stat-row">
          <el-col :xs="24" :md="12" :lg="8" class="cell">
            <el-card class="stat-card">
              <BudgetPanel
                :total-cost="plan.total_cost"
                :total-budget="task.total_budget"
                :days="plan.total_days || spanDays"
                :people-num="task.people_num"
                :budget="plan.itinerary?.budget"
              />
            </el-card>
          </el-col>

          <el-col :xs="24" :md="12" :lg="8" class="cell">
            <el-card class="stat-card">
              <span class="muted">合理性评分</span>
              <el-progress
                class="score"
                type="circle"
                :percentage="score"
                :width="82"
                :stroke-width="7"
                :color="scoreColor"
              >
                <span class="score__value num">{{ score }}</span>
              </el-progress>
              <p v-if="scoreHint" class="score__hint muted">{{ scoreHint }}</p>
            </el-card>
          </el-col>

          <el-col :xs="24" :md="12" :lg="8" class="cell">
            <el-card class="stat-card">
              <span class="muted">行程天气</span>
              <WeatherStrip
                :forecast="plan.itinerary?.weather"
                :summary="plan.weather_summary"
                :advice="plan.itinerary?.weather_advice"
              />
              <div class="stat-card__foot">
                <span>行程天数 {{ plan.total_days || spanDays }} 天</span>
                <span>生成于 {{ formatDateTime(plan.generate_time) }}</span>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <el-card
          v-if="reviewDetail || reviewDimensions.length || reviewSuggestions.length || reviewIssues.length"
          class="block"
        >
          <div class="section-title">评分理由</div>
          <p v-if="reviewDetail" class="block__summary">{{ reviewDetail }}</p>

          <div v-if="reviewDimensions.length" class="review-dims">
            <div v-for="dim in reviewDimensions" :key="dim.name" class="review-dim">
              <div class="review-dim__head">
                <span class="review-dim__name">{{ dim.name }}</span>
                <span class="review-dim__bar">
                  <i
                    :style="{
                      width: `${Math.max(0, Math.min(100, Number(dim.score) || 0))}%`,
                      background: dimColor(dim.score)
                    }"
                  ></i>
                </span>
                <span class="review-dim__score" :style="{ color: dimColor(dim.score) }">{{ dim.score }}</span>
              </div>
              <p v-if="dim.comment" class="review-dim__comment">{{ dim.comment }}</p>
            </div>
          </div>

          <div v-if="reviewSuggestions.length" class="review-suggest">
            <div class="review-suggest__title">可以这样改</div>
            <ol>
              <li v-for="(item, index) in reviewSuggestions" :key="index">{{ item }}</li>
            </ol>
          </div>

          <ul v-if="reviewIssues.length" class="review-issues">
            <li v-for="(issue, index) in reviewIssues" :key="index">{{ issue }}</li>
          </ul>
        </el-card>

        <el-card v-if="research" class="block research-card">
          <el-collapse>
            <el-collapse-item name="research">
              <template #title>
                <span class="research-title">
                  <el-icon :size="14"><Document /></el-icon>
                  数据来源（联网查询）：门票、住宿、餐饮价格取自下列工具返回的原始数据
                </span>
              </template>
              <pre class="research-text">{{ research }}</pre>
            </el-collapse-item>
          </el-collapse>
        </el-card>

        <el-card class="block">
          <div class="section-title">每日行程</div>
          <div v-if="summaryParas.length" class="block__summary paras">
            <p v-for="(para, index) in summaryParas" :key="`summary-${index}`" class="para">
              <strong v-if="para.lead" class="para__lead">{{ para.lead }}</strong>{{ para.text }}
            </p>
          </div>

          <div class="days">
            <article v-for="day in dayPlans" :key="day.day" class="day">
              <header class="day__head">
                <span class="day__badge">
                  <strong>D{{ day.day }}</strong>
                  <small>{{ shortDate(day.date) || `第 ${day.day} 天` }}</small>
                </span>
                <WeatherTag
                  v-if="weatherOf(day)"
                  :weather="weatherOf(day).weather"
                  :temp-min="weatherOf(day).temp_min"
                  :temp-max="weatherOf(day).temp_max"
                />
              </header>

              <div class="day__body">
                <div v-if="parasOf(day).length" class="day__desc paras">
                  <p v-for="(para, index) in parasOf(day)" :key="`desc-${index}`" class="para">
                    <strong v-if="para.lead" class="para__lead">{{ para.lead }}</strong>{{ para.text }}
                  </p>
                </div>

                <div v-if="spotsOf(day).length" class="day__row">
                  <span class="day__label"><el-icon :size="13"><Location /></el-icon>景点</span>
                  <ul class="spots">
                    <li v-for="(spot, index) in spotsOf(day)" :key="`${spot.name}-${index}`" class="spot">
                      <span class="spot__index num">{{ index + 1 }}</span>
                      <span class="spot__name">{{ spot.name }}</span>
                      <span v-if="spot.ticket !== undefined && spot.ticket !== null" class="spot__meta">
                        {{ formatTicket(spot.ticket) }}
                      </span>
                      <span v-else-if="'ticket' in spot" class="spot__meta spot__meta--unknown">
                        票价以官方为准
                      </span>
                      <span v-if="spot.start_time" class="spot__meta">{{ spot.start_time }} 到达</span>
                      <span v-if="spot.duration_minutes" class="spot__meta">
                        建议游玩 {{ formatDuration(spot.duration_minutes) }}
                      </span>
                      <small v-if="reasonOf(day, spot.name)" class="spot__reason">
                        {{ reasonOf(day, spot.name) }}
                      </small>
                    </li>
                  </ul>
                </div>

                <div v-if="mealsOf(day).length" class="day__row">
                  <span class="day__label"><el-icon :size="13"><ForkSpoon /></el-icon>餐饮</span>
                  <ul class="meals">
                    <li v-for="(meal, index) in mealsOf(day)" :key="`${meal.name}-${index}`" class="meal">
                      <div class="meal__line">
                        <span class="meal__name">{{ meal.name }}</span>
                        <span v-if="meal.cost" class="meal__meta num">人均 {{ formatMoney(meal.cost) }}</span>
                        <span v-else-if="'cost' in meal" class="meal__meta">人均待确认</span>
                      </div>
                      <small v-if="meal.reason" class="meal__reason">{{ meal.reason }}</small>
                    </li>
                  </ul>
                </div>

                <div v-if="day.hotel" class="day__row">
                  <span class="day__label"><el-icon :size="13"><House /></el-icon>住宿</span>
                  <span>{{ day.hotel }}</span>
                </div>

                <div v-if="day.transport" class="day__row">
                  <span class="day__label"><el-icon :size="13"><Van /></el-icon>交通</span>
                  <span>{{ day.transport }}</span>
                </div>

                <div v-if="day.route && day.route.optimized" class="day__row">
                  <span class="day__label"><el-icon :size="13"><Guide /></el-icon>路线</span>
                  <div class="route">
                    <div class="route__head">
                      <span class="route__summary">{{ day.route.summary }}</span>
                      <span v-if="day.route.reordered" class="route__tag">已按顺路重排</span>
                    </div>
                    <div v-if="day.route.congestion" class="route__meta">
                      实时路况：{{ day.route.congestion }}
                    </div>
                    <div v-if="day.route.advice" class="route__meta route__meta--advice">
                      {{ day.route.advice }}
                    </div>
                  </div>
                </div>
                <div v-else-if="day.route && day.route.note" class="day__row">
                  <span class="day__label"><el-icon :size="13"><Guide /></el-icon>路线</span>
                  <span class="route__meta">{{ day.route.note }}</span>
                </div>
              </div>
            </article>
          </div>
        </el-card>

        <el-card class="block">
          <div class="section-title">地图分布</div>
          <MapView :itinerary="dayPlans" :destination="task.destination" :height="420" />
        </el-card>
      </template>

      <el-card v-else class="state-card">
        <el-result
          icon="warning"
          title="方案数据缺失"
          sub-title="任务标记为已完成，但没有取到行程数据，可以重新生成"
        >
          <template #extra>
            <el-button type="primary" :icon="RefreshRight" :loading="regenerating" @click="regenerate">
              重新生成
            </el-button>
          </template>
        </el-result>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Calendar,
  Document,
  ForkSpoon,
  Guide,
  House,
  Loading,
  Location,
  Refresh,
  RefreshRight,
  Van,
} from '@element-plus/icons-vue'
import BudgetPanel from '../components/BudgetPanel.vue'
import MapView from '../components/MapView.vue'
import WeatherStrip from '../components/WeatherStrip.vue'
import WeatherTag from '../components/WeatherTag.vue'
import { generatePlan, getTaskDetail } from '../api/travel'
import {
  calcDays,
  calcNights,
  coverGradient,
  coverImage,
  formatDateRange,
  formatDateTime,
  formatDuration,
  formatMoney,
  formatTicket,
  isFinished,
  normalizeMeals,
  normalizeSpots,
  peopleSummary,
  statusTagType,
  statusText,
} from '../utils/format'

const POLL_INTERVAL = 3000

const route = useRoute()
const router = useRouter()
const taskId = route.params.id

const task = ref(null)
const loading = ref(true)
const refreshing = ref(false)
const regenerating = ref(false)

let timer = null

const plan = computed(() => task.value?.plan || null)
const dayPlans = computed(() => plan.value?.itinerary?.days || [])
const research = computed(() => plan.value?.itinerary?.research || '')

// 行程说明按内容重点拆段。模型经常把整段说明写成一行（没有换行），
// 所以不能只按 \n\n 拆，这里按「内容重点」的信号逐级拆分：
// 1) 句末标点后的换行；2) ①②③ 这类序号；3)「预算方面：」这类话题引导语；
// 4) 仍然过长的段落按句子再切，保证不会出现一整屏连成一片
const PARA_MARK = '\u0000' // 正文不会出现的分隔符，最后按它拆段
const MAX_PARA = 150 // 单段长度上限，超过就按句子断开
const ENUM_CHARS = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'
const SENTENCE_CHARS = '。！？；!?;'
const CLAUSE_CHARS = '，、,'
const LEAD_PATTERN = /^([^。！？；：!?;]{2,16}：)/

// 中文行合并时不该插空格，只有两侧都是英文/数字时才补一个空格
const joinLine = (buffer, text) =>
  /[A-Za-z0-9]$/.test(buffer) && /^[A-Za-z0-9]/.test(text) ? `${buffer} ${text}` : buffer + text

const splitBy = (text, chars) => text.match(new RegExp(`[^${chars}]+[${chars}]?`, 'g')) || [text]

// 一段还是太长时，先按句末标点切，仍超长再退一步按逗号切
const splitLongPara = (para) => {
  const out = []
  for (const sentence of splitBy(para, SENTENCE_CHARS)) {
    if (sentence.length <= MAX_PARA) {
      out.push(sentence)
      continue
    }
    let buffer = ''
    for (const clause of splitBy(sentence, CLAUSE_CHARS)) {
      if (buffer && (buffer + clause).length > MAX_PARA) {
        out.push(buffer)
        buffer = clause
      } else {
        buffer += clause
      }
    }
    if (buffer) out.push(buffer)
  }
  return out
}

const splitParas = (text) => {
  let source = String(text || '')
    .replace(/\r\n?/g, '\n')
    .trim()
  if (!source) return []

  // 1) 句末标点后的换行就是分段点（其余换行稍后合并成空格）
  source = source.replace(/([。！？；：!?;:])\s*\n\s*/g, `$1${PARA_MARK}`)
  // 2) ①②③ 这类序号另起一段
  source = source.replace(
    new RegExp(`([。！？；：!?;:])\\s*(?=[${ENUM_CHARS}])`, 'g'),
    `$1${PARA_MARK}`
  )
  // 3)「预算方面：」「价格待现场确认的有：」这类话题引导语另起一段
  source = source.replace(
    new RegExp(`([${SENTENCE_CHARS}])\\s*(?=[^。！？；：!?;\\n]{2,16}：)`, 'g'),
    `$1${PARA_MARK}`
  )

  return source
    .split(PARA_MARK)
    .flatMap((chunk) => chunk.split(/\n\s*\n+/))
    .map((para) => para.split('\n').reduce((acc, line) => (acc ? joinLine(acc, line.trim()) : line.trim()), ''))
    .map((para) => para.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .flatMap(splitLongPara)
}

// 段落开头的「预算方面：」这类引导语单独加粗，方便一眼扫到重点
const toParagraphs = (text) =>
  splitParas(text).map((para) => {
    const lead = para.match(LEAD_PATTERN)
    return lead ? { lead: lead[1], text: para.slice(lead[1].length) } : { lead: '', text: para }
  })

const summaryParas = computed(() => toParagraphs(plan.value?.itinerary?.summary))
const parasOf = (day) => toParagraphs(day?.description)

// 老方案的景点/餐饮是纯字符串，这里统一成对象，两种格式都能渲染
const spotsOf = (day) => normalizeSpots(day?.spots)
const mealsOf = (day) => normalizeMeals(day?.meals)

// 路线 Agent 给每个景点写的排序理由，按名称对齐
const reasonOf = (day, name) => {
  const stops = day?.route?.stops
  if (!Array.isArray(stops) || !name) return ''
  return stops.find((stop) => stop?.name === name)?.reason || ''
}
const shortDate = (date) => String(date || '').slice(5)

// 按日期把逐日天气对齐到当天
const weatherOf = (day) => {
  const forecast = plan.value?.itinerary?.weather
  if (!day?.date || !Array.isArray(forecast)) return null
  return forecast.find((item) => item?.date === day.date) || null
}
const isRunning = computed(() => task.value?.status === 'pending' || task.value?.status === 'generating')

const spanDays = computed(() => calcDays(task.value?.start_date, task.value?.end_date))
const spanNights = computed(() => calcNights(task.value?.start_date, task.value?.end_date))

const score = computed(() => Math.max(0, Math.min(100, Number(plan.value?.reason_score) || 0)))
const scoreColor = computed(() =>
  score.value >= 85 ? 'var(--success)' : score.value >= 70 ? 'var(--warning)' : 'var(--danger)'
)
// 评分理由完全由评审模型生成并随行程落库，这里只做展示
const review = computed(() => plan.value?.itinerary?.review || null)
const scoreHint = computed(() => review.value?.summary || '')
const reviewDetail = computed(() => review.value?.explanation || '')
const reviewIssues = computed(() => review.value?.issues || [])
// 五个主观维度的打分与建议：分数由评审模型给，总分由后端按权重算出
const reviewDimensions = computed(() => (review.value?.dimensions || []).filter((item) => item?.name))
const reviewSuggestions = computed(() => review.value?.suggestions || [])
const dimColor = (value) => {
  const num = Number(value) || 0
  return num >= 85 ? 'var(--success)' : num >= 70 ? 'var(--warning)' : 'var(--danger)'
}

const heroStyle = computed(() => {
  const destination = task.value?.destination || ''
  const image = coverImage(destination)
  const layer = 'linear-gradient(180deg, rgba(0,0,0,.42), rgba(0,0,0,.10) 55%, rgba(0,0,0,.34))'
  return image
    ? { backgroundImage: `${layer}, url(${image})` }
    : { background: coverGradient(destination) }
})

const stopPolling = () => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

// 详情接口同时返回状态与方案，只用一个接口轮询，避免两个接口状态不一致
const fetchDetail = async ({ silent = false } = {}) => {
  if (!silent) loading.value = true
  try {
    task.value = await getTaskDetail(taskId)
    if (isFinished(task.value.status)) stopPolling()
  } catch {
    if (!silent) task.value = null
  } finally {
    if (!silent) loading.value = false
  }
}

const startPolling = () => {
  stopPolling()
  timer = setInterval(() => fetchDetail({ silent: true }), POLL_INTERVAL)
}

const refresh = async () => {
  refreshing.value = true
  try {
    await fetchDetail({ silent: true })
  } finally {
    refreshing.value = false
  }
}

const regenerate = async () => {
  regenerating.value = true
  try {
    await generatePlan(taskId)
    ElMessage.success('已重新提交生成')
    await fetchDetail({ silent: true })
    if (isRunning.value) startPolling()
  } catch {
    // 例如「行程正在生成中，请勿重复提交」，拦截器已提示
  } finally {
    regenerating.value = false
  }
}

onMounted(async () => {
  await fetchDetail()
  if (task.value && !isFinished(task.value.status)) startPolling()
})

onUnmounted(stopPolling)
</script>

<style scoped>
.hero {
  position: relative;
  padding: 22px 24px 24px;
  border-radius: var(--radius-lg);
  background-size: cover;
  background-position: center;
  color: #fff;
  box-shadow: var(--shadow-md);
  overflow: hidden;
}

.hero::after {
  content: '';
  position: absolute;
  right: -90px;
  top: -110px;
  width: 300px;
  height: 300px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
}

.hero__back {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px 5px 8px;
  border-radius: var(--radius-pill);
  border: 1px solid rgba(255, 255, 255, 0.32);
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
  font-size: 12.5px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.hero__back:hover {
  background: rgba(255, 255, 255, 0.3);
}

.hero__title {
  position: relative;
  z-index: 1;
  margin: 14px 0 6px;
  color: #fff;
  font-size: 28px;
  letter-spacing: -0.4px;
}

.hero__meta {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0 0 14px;
  color: rgba(255, 255, 255, 0.88);
  font-size: 13.5px;
}

.hero__dot {
  margin: 0 2px;
  opacity: 0.6;
}

.hero__tags {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.hero__chip {
  padding: 3px 11px;
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.26);
  font-size: 12px;
}

.state-card {
  margin-top: 18px;
}

.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 28px 20px 34px;
  text-align: center;
}

.state__icon {
  color: var(--brand-500);
}

.state p {
  max-width: 460px;
  margin: 0;
  color: var(--text-3);
  font-size: 13px;
  line-height: 1.7;
}

.state__steps {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin: 4px 0 6px;
}

.state small {
  font-size: 12px;
}

.is-spin {
  animation: spin 1.1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.stat-row {
  margin-top: 18px;
}

.cell {
  margin-bottom: 18px;
}

.stat-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 13px;
}

.score {
  align-self: center;
}

.score__value {
  font-size: 21px;
  font-weight: 600;
  color: var(--text-1);
}

.score__hint {
  margin: 0;
  text-align: center;
  font-size: 12.5px;
}

.weather {
  margin-top: 2px;
}

.stat-card__foot {
  margin-top: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-1);
  color: var(--text-3);
  font-size: 12.5px;
}

.block {
  margin-bottom: 18px;
}

.block__summary {
  margin: -4px 0 18px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--grad-brand-soft);
  color: var(--text-2);
  font-size: 13.5px;
  line-height: 1.7;
}

/* 分段后的行程说明：段与段之间留出空档，读起来是一个个重点而不是一大段 */
.paras {
  display: grid;
  gap: 10px;
}

.paras .para {
  margin: 0;
  line-height: 1.75;
}

.paras .para + .para {
  padding-top: 10px;
  border-top: 1px solid var(--border-1);
}

/* 段落开头的话题引导语（如「预算方面：」）加粗，方便快速扫到重点 */
.para__lead {
  color: var(--brand-600);
  font-weight: 600;
}

.review-issues {
  margin: 0;
  padding-left: 18px;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.8;
}

/* 五个主观维度的打分：名称 + 进度条 + 分数，下面跟一句短评 */
.review-dims {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.review-dim__head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.review-dim__name {
  flex: none;
  width: 3em;
  color: var(--text-1);
  font-size: 13px;
  font-weight: 600;
}

.review-dim__bar {
  flex: 1;
  height: 6px;
  border-radius: 999px;
  background: var(--border-1);
  overflow: hidden;
}

.review-dim__bar > i {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 0.4s ease;
}

.review-dim__score {
  flex: none;
  width: 2.4em;
  text-align: right;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.review-dim__comment {
  margin: 4px 0 0 0;
  padding-left: calc(3em + 10px);
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.6;
}

/* 可执行的修改建议，和上面的问题清单区分开 */
.review-suggest {
  margin-top: 16px;
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--brand-50, rgba(64, 128, 255, 0.06));
  border: 1px solid var(--border-1);
}

.review-suggest__title {
  margin-bottom: 6px;
  color: var(--brand-600);
  font-size: 13px;
  font-weight: 600;
}

.review-suggest ol {
  margin: 0;
  padding-left: 18px;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.8;
}

.days {
  display: grid;
  gap: 12px;
}

.day {
  display: flex;
  flex-direction: column;
  gap: 11px;
  padding: 14px 16px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius-md);
  background: var(--card);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.day:hover {
  border-color: var(--brand-400);
  box-shadow: var(--shadow-sm);
}

.day__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--border-1);
}

.day__badge {
  display: inline-flex;
  align-items: baseline;
  gap: 7px;
  padding: 3px 11px;
  border-radius: var(--radius-pill);
  background: var(--grad-brand-soft);
  color: var(--brand-600);
}

.day__badge strong {
  font-size: 15px;
  font-family: var(--font-num);
}

.day__badge small {
  font-size: 11.5px;
  color: var(--text-3);
}

.day__body {
  display: grid;
  gap: 10px;
  min-width: 0;
}

/* 当天行程说明：分段落展示，与下面的景点/餐饮明细区分开 */
.day__desc {
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  background: var(--grad-brand-soft);
  color: var(--text-2);
  font-size: 13px;
}

.day__desc.paras {
  gap: 8px;
}

.day__desc .para + .para {
  padding-top: 8px;
}

.day__row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13.5px;
  color: var(--text-2);
}

.day__label {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: 52px;
  padding-top: 1px;
  color: var(--text-3);
  font-size: 12.5px;
}

.spots,
.meals {
  flex: 1;
  min-width: 0;
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 7px;
}

.spot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.spot__index {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--bg-soft);
  border: 1px solid var(--border-1);
  color: var(--text-3);
  font-size: 11px;
}

.spot__name {
  color: var(--text-1);
  font-weight: 500;
}

.spot__meta {
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  background: var(--bg-soft);
  color: var(--text-3);
  font-size: 11.5px;
}

.spot__meta--unknown {
  background: transparent;
  border: 1px dashed var(--border-2);
}

/* 路线 Agent 给出的排序理由，独占一行排在景点名下方 */
.spot__reason {
  flex-basis: 100%;
  padding-left: 26px;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.5;
}

.route {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 4px;
}

.route__head {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
}

.route__summary {
  color: var(--text-1);
}

.route__tag {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-600);
  font-size: 11.5px;
}

.route__meta {
  color: var(--text-3);
  font-size: 12.5px;
  line-height: 1.6;
}

.route__meta--advice {
  color: var(--brand-600);
}

.research-card :deep(.el-collapse) {
  border: none;
}

.research-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-2);
  font-size: 13.5px;
}

.research-text {
  margin: 0;
  padding: 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
  color: var(--text-2);
  font-family: var(--font-sans);
  font-size: 12.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 420px;
  overflow-y: auto;
}

.meal__line {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
}

.meal__name {
  color: var(--text-1);
  font-weight: 500;
}

.meal__meta {
  color: var(--text-3);
  font-size: 11.5px;
}

.meal__reason {
  display: block;
  margin-top: 2px;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.55;
}

@media (max-width: 640px) {
  .hero {
    padding: 18px 16px 20px;
  }

  .hero__title {
    font-size: 22px;
  }

  .day__label {
    width: 44px;
  }
}
</style>
