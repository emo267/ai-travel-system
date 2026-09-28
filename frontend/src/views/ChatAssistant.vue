<template>
  <div class="page chat-page">
    <div class="surface chat-layout">
      <aside class="chat-side">
        <div class="section-title">助手设置</div>

        <div class="side-group">
          <span class="side-group__label">性格</span>
          <el-radio-group v-model="prefs.persona" class="side-group__list">
            <el-radio v-for="item in PERSONAS" :key="item.value" :value="item.value">
              {{ item.label }}
            </el-radio>
          </el-radio-group>
          <el-input
            v-if="prefs.persona === 'custom'"
            v-model="prefs.customPersona"
            type="textarea"
            :rows="3"
            :maxlength="120"
            show-word-limit
            resize="none"
            placeholder="例如：像老朋友一样聊天，多讲当地人怎么玩，少讲套话"
          />
        </div>

        <div class="side-group">
          <span class="side-group__label">回答长度</span>
          <el-radio-group v-model="prefs.answerLength" class="side-group__list">
            <el-radio v-for="item in LENGTHS" :key="item.value" :value="item.value">
              {{ item.label }}
            </el-radio>
          </el-radio-group>
        </div>

        <div class="side-group side-group--row">
          <span class="side-group__label">显示知识库引用</span>
          <el-switch v-model="prefs.showSources" size="small" />
        </div>

        <div class="conv">
          <div class="conv__head">
            <span class="side-group__label">会话历史</span>
            <el-button
              size="small"
              text
              :icon="Plus"
              :disabled="isStreaming"
              @click="newConversation"
            >
              新建对话
            </el-button>
          </div>

          <div class="conv__list">
            <p v-if="!conversations.length" class="conv__empty muted">
              还没有历史会话，发出第一条消息就会自动保存
            </p>
            <div
              v-for="conversation in conversations"
              :key="conversation.conversation_id"
              class="conv__item"
              :class="{ 'conv__item--active': conversation.conversation_id === activeId }"
              @click="openConversation(conversation)"
            >
              <span class="conv__title">{{ conversation.title }}</span>
              <span class="conv__time">{{ formatDateTime(conversation.create_time) }}</span>
              <el-icon
                class="conv__del"
                :size="12"
                @click.stop="removeConversation(conversation)"
              >
                <Close />
              </el-icon>
            </div>
          </div>
        </div>

        <p class="chat-side__hint muted">每个会话独立保存设置，账号默认取自最近一次会话</p>
      </aside>

      <section class="chat-main">
        <div class="chat-head">
          <div class="row-between">
            <div class="section-title chat-head__title">AI 旅行助手</div>
            <el-select
              v-model="taskId"
              class="chat-head__select"
              placeholder="关联某份行程（可选）"
              clearable
            >
              <el-option
                v-for="t in tasks"
                :key="t.task_id"
                :label="`${t.destination} · ${formatDateRange(t.start_date, t.end_date)}`"
                :value="t.task_id"
              />
            </el-select>
          </div>
          <p class="chat-head__hint muted">关联行程后，助手会先读这份行程再回答，需要实时信息时才联网核实</p>
        </div>

        <ChatBox :messages="messages" :show-sources="prefs.showSources" />

        <div v-if="showPrompts" class="prompts">
          <button
            v-for="prompt in QUICK_PROMPTS"
            :key="prompt"
            type="button"
            class="prompt"
            @click="askQuick(prompt)"
          >
            {{ prompt }}
          </button>
        </div>

        <div class="chat-foot">
          <el-input
            v-model="inputMessage"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            resize="none"
            placeholder="输入问题，Enter 发送，Shift + Enter 换行"
            :disabled="isStreaming"
            @keydown.enter.exact.prevent="sendMessage"
          />
          <el-button
            v-if="isStreaming"
            class="chat-foot__stop"
            :icon="CircleClose"
            @click="stopStreaming"
          >
            停止生成
          </el-button>
          <el-button
            v-else
            type="primary"
            class="chat-foot__send"
            :icon="Promotion"
            :disabled="!inputMessage.trim()"
            @click="sendMessage"
          >
            发送
          </el-button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleClose, Close, Plus, Promotion } from '@element-plus/icons-vue'
import ChatBox from '../components/ChatBox.vue'
import {
  deleteConversation,
  getChatPreferences,
  getConversationMessages,
  listConversations,
  streamChat,
  updateChatPreferences,
  updateConversation,
} from '../api/chat'
import { getTasks } from '../api/travel'
import { formatDateRange, formatDateTime } from '../utils/format'

const GREETING = '你好！我是你的 AI 旅行助手。可以问我目的地攻略、避坑建议，也可以让我点评某份行程的预算与节奏。'

const QUICK_PROMPTS = [
  '去北京要注意什么？',
  '第一次自由行，怎么安排交通最省心？',
  '3 天时间怎么安排比较合理？',
  '有哪些当地美食值得专门去一趟？',
]

const PERSONAS = [
  { value: 'professional', label: '专业严谨' },
  { value: 'humorous', label: '幽默风趣' },
  { value: 'caring', label: '贴心细致' },
  { value: 'concise', label: '简洁高效' },
  { value: 'custom', label: '自定义' },
]

const LENGTHS = [
  { value: 'short', label: '简洁' },
  { value: 'medium', label: '适中' },
  { value: 'long', label: '详细' },
]

// 与后端 PreferenceIn 的默认值一致：账号还没设置过时后端会落这份默认值
const DEFAULT_PREFS = {
  persona: 'professional',
  customPersona: '',
  answerLength: 'medium',
  showSources: true,
}

// 每项都是新对象：加载历史会话时整段替换 messages，别让问候语被几处共享
const greetingMessage = () => ({ role: 'assistant', content: GREETING, sources: [] })

const messages = ref([greetingMessage()])
const inputMessage = ref('')
const isStreaming = ref(false)
const taskId = ref(null)
const tasks = ref([])
const prefs = reactive({ ...DEFAULT_PREFS })
const conversations = ref([])
// null 表示「还没落库的新对话画布」：只有问候语和快捷问题，发出第一条消息才会建会话
const activeId = ref(null)

let controller = null
let activeReply = null
let watchdog = null

// 兜底：长时间收不到任何事件就认为连接断了，主动结束，避免界面永远停在“正在输出”
const WATCHDOG_MS = 45000

const resetWatchdog = () => {
  clearTimeout(watchdog)
  watchdog = setTimeout(() => {
    if (!activeReply) return
    activeReply.stopped = true
    controller?.abort()
  }, WATCHDOG_MS)
}

const clearWatchdog = () => {
  clearTimeout(watchdog)
  watchdog = null
}

// 设置改动写回当前账号。自定义性格是输入框，会连续触发 watch，合并成一次请求
const SAVE_DEBOUNCE_MS = 500
const CUSTOM_PERSONA_LIMIT = 120

let syncEnabled = false // 从后端读回设置时也会触发 watch，这之前不回写
let saveTimer = null
let pendingSave = null

const toApiPrefs = () => ({
  persona: prefs.persona,
  custom_persona: prefs.customPersona.slice(0, CUSTOM_PERSONA_LIMIT),
  answer_length: prefs.answerLength,
  show_sources: prefs.showSources,
})

// 从后端读回设置时也会触发 watch：赋值期间关掉回写，否则会「打开会话即保存」一个假改动
const applyPrefs = async (source) => {
  syncEnabled = false
  Object.assign(prefs, source)
  await nextTick()
  syncEnabled = true
}

// 失败提示由 axios 响应拦截器统一弹出，这里只管别把异常抛出去
const flushSave = () => {
  clearTimeout(saveTimer)
  if (!pendingSave) return
  const payload = pendingSave
  pendingSave = null
  // 目标在「发送这一刻」取，和 watch 触发时无关：有会话就写会话自己的设置，
  // 还在新画布上就写账号设置（下一个新会话会继承它）
  const target = activeId.value
  const call = target
    ? updateConversation(target, payload)
    : updateChatPreferences(payload)
  call.catch(() => {})
}

watch(
  prefs,
  () => {
    if (!syncEnabled) return
    pendingSave = toApiPrefs()
    clearTimeout(saveTimer)
    saveTimer = setTimeout(flushSave, SAVE_DEBOUNCE_MS)
  },
  { deep: true }
)

// 刚改完就离开页面时别把这次改动丢掉；已退出登录则不再补发，避免误报登录过期
onBeforeUnmount(() => {
  if (localStorage.getItem('access_token')) flushSave()
  else clearTimeout(saveTimer)
})

const showPrompts = computed(() => messages.value.length <= 1 && !isStreaming.value)

const askQuick = (prompt) => {
  inputMessage.value = prompt
  sendMessage()
}

const refreshList = async () => {
  try {
    conversations.value = await listConversations()
  } catch {
    // 列表拉取失败不影响正在进行的对话
  }
}

// 把账号默认设置读进面板（新建会话时用，它继承的就是账号设置）
const loadAccountPrefs = async () => {
  try {
    const saved = await getChatPreferences()
    await applyPrefs({
      persona: saved.persona,
      customPersona: saved.custom_persona,
      answerLength: saved.answer_length,
      showSources: saved.show_sources,
    })
  } catch {
    // 读不到就沿用当前面板的值，同步开关一定要放开，否则后续改动永远不回写
    syncEnabled = true
  }
}

// 回到「还没有会话」的画布，不碰防抖队列
const resetToNewCanvas = async () => {
  activeId.value = null
  taskId.value = null
  messages.value = [greetingMessage()]
  await loadAccountPrefs()
}

const newConversation = async () => {
  if (isStreaming.value) return
  flushSave() // 必须第一句：防抖目标取的是当前 activeId
  await resetToNewCanvas()
}

const openConversation = async (conversation) => {
  if (isStreaming.value) {
    ElMessage.warning('正在生成回复，请等这次回答结束后再切换会话')
    return
  }
  const conversationId = conversation.conversation_id
  if (conversationId === activeId.value) return
  flushSave() // 必须第一句，理由同上

  // records 必须声明在 try 外面：声明在 try 里的话块级作用域会让下面的 .map 直接
  // 抛 ReferenceError，而且这种错构建期不报、页面也不弹提示，只会表现为「点了没反应」
  let records
  try {
    records = await getConversationMessages(conversationId)
  } catch {
    // 会话已被删除或不属于当前账号：刷新列表后退回新画布
    await refreshList()
    await resetToNewCanvas()
    return
  }

  // 先铺消息再认这个会话：万一中间出错，activeId 没被改掉，用户还能再点一次
  messages.value = [
    greetingMessage(),
    ...records.map((record) => ({ role: record.role, content: record.content, sources: [] })),
  ]
  activeId.value = conversationId
  taskId.value = null
  // 历史会话要跟着自己的助手设置
  await applyPrefs({
    persona: conversation.persona,
    customPersona: conversation.custom_persona,
    answerLength: conversation.answer_length,
    showSources: conversation.show_sources,
  })
}

const removeConversation = async (conversation) => {
  try {
    await ElMessageBox.confirm(
      `删除会话「${conversation.title}」？该会话的消息会一并删除。`,
      '删除会话',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return // 用户点了取消
  }

  flushSave() // 会话马上要没了，别让待发的改动 PATCH 到一个已删除的会话上
  try {
    await deleteConversation(conversation.conversation_id)
  } catch {
    return
  }
  ElMessage.success('已删除')
  await refreshList()

  if (activeId.value !== conversation.conversation_id) return
  activeId.value = null
  if (conversations.value.length) {
    await openConversation(conversations.value[0])
  } else {
    await resetToNewCanvas()
  }
}

const finishReply = () => {
  clearWatchdog()
  if (activeReply) {
    activeReply.loading = false
    activeReply.status = ''
  }
  isStreaming.value = false
  controller = null
  activeReply = null
}

const stopStreaming = () => {
  controller?.abort()
}

const sendMessage = async () => {
  const content = inputMessage.value.trim()
  if (!content || isStreaming.value) return

  messages.value.push({ role: 'user', content, sources: [] })
  inputMessage.value = ''

  // 必须用 reactive：直接改原始对象不会触发 Vue 更新，
  // 之前的表现就是"回答已经在流里回来了，界面却一直停在正在搜索/转圈"
  const reply = reactive({
    role: 'assistant',
    content: '',
    sources: [],
    loading: true,
    stopped: false,
    status: '',
  })
  messages.value.push(reply)
  isStreaming.value = true
  activeReply = reply
  controller = new AbortController()
  resetWatchdog()

  await streamChat(
    content,
    taskId.value,
    {
      onMessage: (text) => {
        resetWatchdog()
        reply.content += text
        reply.status = ''
      },
      onSources: (sources) => {
        resetWatchdog()
        reply.sources = sources
      },
      onStatus: (text) => {
        resetWatchdog()
        reply.status = text
      },
      onConversation: async (id) => {
        // 新会话是服务端懒创建的，首帧把 id 送回来，前端靠它把会话选进侧栏
        if (!id || activeId.value === id) return
        activeId.value = id
        await refreshList()
      },
      onDone: finishReply,
      onAbort: () => {
        reply.stopped = true
        finishReply()
      },
      onError: (err) => {
        ElMessage.error('对话失败：' + err.message)
        finishReply()
      },
    },
    {
      persona: prefs.persona,
      customPersona: prefs.customPersona,
      answerLength: prefs.answerLength,
      conversationId: activeId.value,
      signal: controller.signal,
    }
  )
}

onMounted(async () => {
  try {
    tasks.value = await getTasks()
  } catch {
    // 关联行程是可选项，拉取失败不影响对话
  }

  // 打开最近活跃的那个会话（设置会跟着它一起加载出来）；
  // 一条会话都没有才需要读账号默认设置，它就是此刻面板上的值
  await refreshList()
  if (conversations.value.length) {
    await openConversation(conversations.value[0])
  } else {
    await loadAccountPrefs()
  }
})
</script>

<style scoped>
.chat-page {
  height: calc(100vh - var(--header-h) - 74px);
  min-height: 460px;
}

.chat-layout {
  height: 100%;
  display: flex;
  overflow: hidden;
}

.chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.chat-head {
  padding: 14px 18px 12px;
  border-bottom: 1px solid var(--border-1);
}

.chat-head__title {
  margin-bottom: 0;
}

.chat-head__select {
  width: 240px;
}

.chat-head__hint {
  margin: 6px 0 0;
  font-size: 12px;
}

.prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 18px 12px;
}

.prompt {
  padding: 6px 13px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-1);
  background: var(--card);
  color: var(--text-2);
  font-size: 12.5px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.prompt:hover {
  border-color: var(--brand-400);
  color: var(--brand-600);
  background: var(--grad-brand-soft);
}

.chat-foot {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 12px 18px 16px;
  border-top: 1px solid var(--border-1);
}

.chat-foot__send {
  flex-shrink: 0;
  height: 36px;
  background: var(--grad-brand);
  border: none;
}

.chat-foot__stop {
  flex-shrink: 0;
  height: 36px;
  border-color: var(--danger);
  color: var(--danger);
  background: transparent;
}

.chat-foot__stop:hover {
  background: rgba(239, 68, 68, 0.08);
  border-color: var(--danger);
  color: var(--danger);
}

.chat-side {
  width: 248px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 14px 16px 18px;
  border-right: 1px solid var(--border-1);
  background: var(--bg-soft);
  /* 不能再用 overflow-y:auto —— 父层先滚的话，下面会话列表的内层滚动就永远不生效 */
  overflow: hidden;
}

.conv {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  gap: 8px;
}

.conv__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.conv__list {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.conv__empty {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
}

.conv__item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-1);
  background: var(--card);
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

/* 沿用 .prompt 的悬停语言 */
.conv__item:hover,
.conv__item--active {
  border-color: var(--brand-400);
  color: var(--brand-600);
  background: var(--grad-brand-soft);
}

.conv__title {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.conv__time {
  font-size: 11px;
  color: var(--text-3);
}

.conv__del {
  position: absolute;
  top: 6px;
  right: 6px;
  padding: 2px;
  border-radius: var(--radius-sm);
  color: var(--text-3);
  opacity: 0;
  transition: all 0.2s ease;
}

.conv__item:hover .conv__del {
  opacity: 1;
}

.conv__del:hover {
  color: var(--danger);
  background: rgba(239, 68, 68, 0.08);
}

.side-group {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.side-group--row {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

.side-group__label {
  color: var(--text-2);
  font-size: 12.5px;
  font-weight: 500;
}

.side-group__list {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.side-group__list :deep(.el-radio) {
  height: 22px;
  margin-right: 0;
  font-size: 13px;
}

.chat-side__hint {
  margin: auto 0 0;
  font-size: 11.5px;
  line-height: 1.6;
}

@media (max-width: 900px) {
  .chat-layout {
    flex-direction: column;
    overflow: visible;
  }

  .chat-side {
    width: auto;
    border-right: none;
    border-bottom: 1px solid var(--border-1);
    /* 窄屏整体纵向排列，裁掉内容就没法看了 */
    overflow: visible;
  }

  .conv__list {
    max-height: 200px;
  }

  .side-group__list {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 12px;
  }

  .chat-side__hint {
    margin-top: 0;
  }
}

@media (max-width: 640px) {
  .chat-head__select {
    width: 100%;
  }

  .chat-head .row-between {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
