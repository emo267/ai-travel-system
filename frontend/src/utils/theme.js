import { ref } from 'vue'

const STORAGE_KEY = 'theme'

// 初始状态由 index.html 里的内联脚本决定（避免首屏闪白），这里只读取和切换
const isDark = ref(document.documentElement.classList.contains('dark'))

export const useTheme = () => {
  const toggleTheme = () => {
    isDark.value = !isDark.value
    document.documentElement.classList.toggle('dark', isDark.value)
    localStorage.setItem(STORAGE_KEY, isDark.value ? 'dark' : 'light')
  }

  return { isDark, toggleTheme }
}
