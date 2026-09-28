import {
  Cloudy,
  Drizzling,
  Lightning,
  MostlyCloudy,
  PartlyCloudy,
  Pouring,
  Sunny,
} from '@element-plus/icons-vue'

const coverModules = import.meta.glob('../assets/images/covers/*.{jpg,jpeg,png,webp}', {
  eager: true,
})

const coversByName = Object.fromEntries(
  Object.entries(coverModules).map(([path, mod]) => [
    path
      .split('/')
      .pop()
      .replace(/\.[^.]+$/, '')
      .trim()
      .toLowerCase(),
    mod.default,
  ])
)

const STATUS_TEXT = {
  pending: '待处理',
  generating: '生成中',
  completed: '已完成',
  failed: '失败',
}

const STATUS_TAG = {
  pending: 'info',
  generating: 'warning',
  completed: 'success',
  failed: 'danger',
}

export const STATUS_LIST = Object.entries(STATUS_TEXT).map(([value, label]) => ({ value, label }))

export const statusText = (status) => STATUS_TEXT[status] || status || '未知'

export const statusTagType = (status) => STATUS_TAG[status] || 'info'

export const isFinished = (status) => status === 'completed' || status === 'failed'

export const parseDate = (value) => {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

export const formatDate = (value) => {
  const d = parseDate(value)
  if (!d) return '—'
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

export const formatDateTime = (value) => {
  const d = parseDate(value)
  if (!d) return '—'
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${formatDate(value)} ${hh}:${mi}`
}

export const formatDateRange = (start, end) => {
  if (!start || !end) return '日期待定'
  return `${formatDate(start)} → ${formatDate(end)}`
}

// 出行天数含首尾两天，与后端 total_days 口径一致
export const calcDays = (start, end) => {
  const a = parseDate(start)
  const b = parseDate(end)
  if (!a || !b) return 0
  return Math.max(Math.round((b - a) / 86400000) + 1, 1)
}

export const calcNights = (start, end) => Math.max(calcDays(start, end) - 1, 0)

// 「4 人（男2女2）」；未填性别时退化为「4 人」
export const peopleSummary = (task = {}) => {
  const total = Number(task.people_num) || 0
  const parts = []
  if (task.male_num) parts.push(`男${task.male_num}`)
  if (task.female_num) parts.push(`女${task.female_num}`)
  const breakdown = parts.join('')
  return breakdown ? `${total} 人（${breakdown}）` : `${total} 人`
}

export const formatMoney = (value) => {
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value)
  if (Number.isNaN(n)) return '—'
  return `¥${n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}

// 无本地封面图时按目的地名生成稳定渐变色，同一目的地每次渲染颜色一致
export const coverGradient = (seed = '') => {
  let hash = 0
  for (const ch of String(seed)) {
    hash = (hash * 31 + ch.codePointAt(0)) % 360
  }
  const hue = 148 + (hash % 62)
  return `linear-gradient(135deg, hsl(${hue} 58% 40%), hsl(${(hue + 26) % 360} 68% 56%))`
}

export const coverImage = (destination = '') => {
  const key = String(destination).trim().toLowerCase()
  return coversByName[key] || ''
}

// 和风返回的天气现象文字 → 图标。注意顺序：雷、雨夹雪要先于雨匹配
const WEATHER_ICON_RULES = [
  [/雷/, Lightning],
  [/暴雨|大雨|雨夹雪/, Pouring],
  [/雨/, Drizzling],
  [/雪/, Cloudy],
  [/雾|霾|浮尘|扬沙/, Cloudy],
  [/多云/, PartlyCloudy],
  [/阴/, Cloudy],
  [/晴/, Sunny],
]

export const weatherIcon = (text) => {
  const hit = WEATHER_ICON_RULES.find(([pattern]) => pattern.test(String(text || '')))
  return hit ? hit[1] : MostlyCloudy
}

// 老方案的景点/餐饮是纯字符串，新方案是对象，统一成对象后再渲染
export const normalizeSpots = (spots = []) =>
  (spots || []).map((spot) => (typeof spot === 'string' ? { name: spot } : { ...spot }))

export const normalizeMeals = (meals = []) =>
  (meals || []).map((meal) => (typeof meal === 'string' ? { name: meal } : { ...meal }))

export const formatDuration = (minutes) => {
  const value = Number(minutes)
  if (!value || value <= 0) return ''
  const hours = Math.floor(value / 60)
  const rest = value % 60
  if (!hours) return `${rest} 分钟`
  return rest ? `${hours} 小时 ${rest} 分` : `${hours} 小时`
}

export const formatTicket = (ticket) => {
  const value = Number(ticket)
  if (Number.isNaN(value)) return ''
  return value > 0 ? `参考票价 ${formatMoney(value)}` : '免费'
}
