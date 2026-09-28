import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
})

// 登录/注册接口返回的 401 是"账号或密码不对"的业务结果，不是登录态过期。
// 若也走下面的统一跳转，提示会被整页刷新冲掉，用户只看到界面闪一下。
const AUTH_ENDPOINTS = ['/auth/login', '/auth/register']

// 请求拦截器：自动带上 Token
request.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：统一提示错误，只在登录态真的失效时跳登录页
request.interceptors.response.use(
  response => response.data,
  error => {
    const status = error.response?.status
    const url = error.config?.url || ''
    const isAuthEndpoint = AUTH_ENDPOINTS.some(path => url.includes(path))

    if (status === 401 && !isAuthEndpoint) {
      ElMessage.error('登录已过期，请重新登录')
      localStorage.removeItem('access_token')
      window.location.href = '/login'
      return Promise.reject(error)
    }

    ElMessage.error(pickErrorMessage(error, status))
    return Promise.reject(error)
  }
)

function pickErrorMessage(error, status) {
  if (!error.response) {
    return error.code === 'ECONNABORTED'
      ? '请求超时，请稍后重试'
      : '无法连接后端服务，请确认后端已启动'
  }

  const detail = error.response.data?.detail
  // FastAPI 的 422 校验错误里 detail 是数组，直接塞给 ElMessage 会显示 [object Object]
  if (Array.isArray(detail)) {
    return detail.map(item => item.msg || JSON.stringify(item)).join('；')
  }
  if (typeof detail === 'string' && detail) {
    return detail
  }
  return `请求失败（HTTP ${status}）`
}

export default request
