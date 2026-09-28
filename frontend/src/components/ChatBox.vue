<template>
  <div ref="bodyRef" class="chat-body" @scroll="onScroll">
    <div v-for="(msg, idx) in messages" :key="idx" class="msg" :class="`msg--${msg.role}`">
      <span class="msg__avatar">
        <el-icon :size="15">
          <Promotion v-if="msg.role === 'assistant'" />
          <User v-else />
        </el-icon>
      </span>

      <div class="msg__main">
        <div v-if="showSources && msg.sources?.length" class="sources">
          <button type="button" class="sources__toggle" @click="toggleSources(idx)">
            <el-icon :size="12">
              <ArrowDown v-if="expanded[idx]" />
              <ArrowRight v-else />
            </el-icon>
            引用 {{ msg.sources.length }} 条资料
          </button>
          <div v-show="expanded[idx]" class="sources__list">
            <p v-for="(s, i) in msg.sources" :key="i">{{ s.title }}：{{ s.content }}</p>
          </div>
        </div>

        <div class="bubble">
          <span v-html="formatContent(msg.content)"></span>
          <span v-if="msg.loading && !msg.content && msg.status" class="status">
            <i class="status__dot"></i>{{ msg.status }}
          </span>
          <span v-else-if="msg.loading && !msg.content" class="dots"><i></i><i></i><i></i></span>
          <span v-else-if="msg.loading" class="cursor">▌</span>
        </div>

        <span v-if="msg.stopped" class="stopped">
          <el-icon :size="12"><CircleClose /></el-icon>已停止生成
        </span>
      </div>
    </div>

    <button v-show="!atBottom" type="button" class="to-bottom" @click="scrollToBottom">
      <el-icon :size="14"><ArrowDown /></el-icon>回到最新
    </button>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { ArrowDown, ArrowRight, CircleClose, Promotion, User } from '@element-plus/icons-vue'

const props = defineProps({
  messages: { type: Array, required: true },
  showSources: { type: Boolean, default: true },
})

const bodyRef = ref(null)
const expanded = ref({})
const atBottom = ref(true)

const toggleSources = (idx) => {
  expanded.value[idx] = !expanded.value[idx]
}

const escapeHtml = (text) =>
  String(text).replace(
    /[&<>"']/g,
    (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]
  )

// 模型与知识库内容都会进 v-html，必须先转义再换行，否则是一处 XSS 入口
const formatContent = (text) => escapeHtml(text || '').replace(/\n/g, '<br/>')

const scrollToBottom = () => {
  nextTick(() => {
    const el = bodyRef.value
    if (!el) return
    el.scrollTop = el.scrollHeight
    atBottom.value = true
  })
}

const onScroll = () => {
  const el = bodyRef.value
  if (!el) return
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 60
}

watch(
  () => props.messages,
  () => {
    if (atBottom.value) scrollToBottom()
  },
  { deep: true }
)
</script>

<style scoped>
.chat-body {
  position: relative;
  flex: 1;
  overflow-y: auto;
  padding: 22px 20px;
  background: var(--bg);
  border-radius: var(--radius-md);
  scroll-behavior: smooth;
}

.msg {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.msg--user {
  flex-direction: row-reverse;
}

.msg__avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: var(--grad-brand);
  color: #fff;
  box-shadow: var(--shadow-sm);
}

.msg--user .msg__avatar {
  background: var(--bg-soft);
  border: 1px solid var(--border-1);
  color: var(--text-2);
}

.msg__main {
  max-width: 74%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.msg--user .msg__main {
  align-items: flex-end;
}

.bubble {
  padding: 11px 15px;
  border-radius: 4px 14px 14px 14px;
  background: var(--card);
  border: 1px solid var(--border-1);
  box-shadow: var(--shadow-sm);
  color: var(--text-2);
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
}

.msg--user .bubble {
  border-radius: 14px 4px 14px 14px;
  background: var(--grad-brand);
  border-color: transparent;
  color: #fff;
}

.sources {
  border: 1px solid var(--border-1);
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
  overflow: hidden;
}

.sources__toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  width: 100%;
  padding: 6px 10px;
  border: none;
  background: transparent;
  color: var(--brand-600);
  font-size: 12px;
  cursor: pointer;
}

.sources__list {
  padding: 0 12px 10px;
  display: grid;
  gap: 6px;
}

.sources__list p {
  margin: 0;
  padding-left: 9px;
  border-left: 2px solid var(--brand-400);
  color: var(--text-3);
  font-size: 12.5px;
  line-height: 1.6;
}

.cursor {
  display: inline-block;
  margin-left: 2px;
  animation: blink 1s steps(1) infinite;
}

.stopped {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-3);
  font-size: 11.5px;
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text-3);
  font-size: 13px;
}

.status__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--brand-400);
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.85);
  }
  50% {
    opacity: 1;
    transform: scale(1.1);
  }
}

@keyframes blink {
  0%,
  50% {
    opacity: 1;
  }
  51%,
  100% {
    opacity: 0;
  }
}

.dots {
  display: inline-flex;
  gap: 4px;
  margin-left: 3px;
  vertical-align: middle;
}

.dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-400);
  animation: bounce 1.2s infinite ease-in-out;
}

.dots i:nth-child(2) {
  animation-delay: 0.15s;
}

.dots i:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes bounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.45;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

.to-bottom {
  position: sticky;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0 auto;
  padding: 5px 12px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-1);
  background: var(--card);
  color: var(--text-2);
  font-size: 12px;
  cursor: pointer;
  box-shadow: var(--shadow-md);
}

.to-bottom:hover {
  color: var(--brand-600);
  border-color: var(--brand-400);
}

@media (max-width: 640px) {
  .msg__main {
    max-width: 86%;
  }

  .chat-body {
    padding: 16px 12px;
  }
}
</style>
