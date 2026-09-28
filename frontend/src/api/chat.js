import request from './request'

const BASE_URL = '/api/v1'

export const listConversations = () => request.get('/chat/conversations')

export const getConversationMessages = (conversationId) =>
  request.get(`/chat/conversations/${conversationId}/messages`)

export const updateConversation = (conversationId, data) =>
  request.put(`/chat/conversations/${conversationId}`, data)

export const deleteConversation = (conversationId) =>
  request.delete(`/chat/conversations/${conversationId}`)

export const getChatPreferences = () => request.get('/chat/preferences')

export const updateChatPreferences = (data) => request.put('/chat/preferences', data)

export async function streamChat(message, taskId, callbacks = {}, options = {}) {
  const { onMessage, onSources, onStatus, onDone, onError, onAbort, onConversation } = callbacks
  const { persona, customPersona, answerLength, conversationId, signal } = options
  const token = localStorage.getItem('access_token')

  let response
  try {
    response = await fetch(`${BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        message,
        task_id: taskId || null,
        conversation_id: conversationId || null,
        persona: persona || null,
        custom_persona: persona === 'custom' ? customPersona || null : null,
        answer_length: answerLength || null,
      }),
      signal,
    })
  } catch (error) {
    // 用户主动停止时浏览器抛 AbortError，这不是失败
    if (error?.name === 'AbortError') {
      onAbort?.()
      return
    }
    onError?.(error)
    return
  }

  if (!response.ok) {
    // 这里走的是原生 fetch，拿不到 axios 拦截器的中文提示，自己把 detail 取出来
    const detail = await response.json().catch(() => null)
    onError?.(new Error(detail?.detail || `请求失败（HTTP ${response.status}）`))
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const jsonStr = line.slice(6).trim()
        if (!jsonStr) continue

        try {
          const msg = JSON.parse(jsonStr)
          if (msg.type === 'text') onMessage?.(msg.data)
          else if (msg.type === 'sources') onSources?.(msg.data)
          else if (msg.type === 'status') onStatus?.(msg.data)
          else if (msg.type === 'conversation') onConversation?.(msg.data?.conversation_id)
          else if (msg.type === 'done') onDone?.()
          else if (msg.type === 'error') onError?.(new Error(msg.data))
        } catch (e) {
          console.error('SSE 解析失败', e)
        }
      }
    }
    // 连接意外断开时兜底结束，避免界面一直停在“生成中”
    onDone?.()
  } catch (error) {
    if (error?.name === 'AbortError') {
      onAbort?.()
      return
    }
    onError?.(error)
  }
}
