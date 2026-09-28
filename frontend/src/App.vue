<template>
  <div class="app-shell" :class="{ 'app-shell--bare': isLogin }">
    <header v-if="!isLogin" class="app-header">
      <div class="app-header__inner">
        <div class="brand" @click="router.push('/travel/list')">
          <span class="brand__mark">
            <el-icon :size="19"><Promotion /></el-icon>
          </span>
          <span class="brand__text">
            <strong>旅行计划智能助手</strong>
            <small>AI 行程规划 · 预算核算 · 地图可视化</small>
          </span>
        </div>

        <el-menu class="nav" mode="horizontal" :default-active="activeNav" :ellipsis="false" router>
          <el-menu-item index="/travel/list">历史行程</el-menu-item>
          <el-menu-item index="/travel/create">创建行程</el-menu-item>
          <el-menu-item index="/chat">AI 对话</el-menu-item>
        </el-menu>

        <div class="actions">
          <el-tooltip :content="isDark ? '切换到浅色' : '切换到深色'" placement="bottom">
            <button class="icon-btn" type="button" @click="toggleTheme">
              <el-icon :size="17">
                <Sunny v-if="isDark" />
                <Moon v-else />
              </el-icon>
            </button>
          </el-tooltip>

          <el-dropdown trigger="click" @command="onCommand">
            <span class="user">
              <el-avatar :size="30" class="user__avatar">{{ initial }}</el-avatar>
              <span class="user__name">{{ username }}</span>
              <el-icon :size="12"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </header>

    <main class="app-main" :class="{ 'app-main--bare': isLogin }">
      <router-view v-slot="{ Component }">
        <transition name="fade-slide" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, Moon, Promotion, Sunny, SwitchButton } from '@element-plus/icons-vue'
import { useUserStore } from './store/user'
import { useTheme } from './utils/theme'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const { isDark, toggleTheme } = useTheme()

const isLogin = computed(() => route.path === '/login')

// 详情页在菜单里没有对应项，高亮回「历史行程」
const activeNav = computed(() =>
  route.path.startsWith('/travel/detail') ? '/travel/list' : route.path
)

const username = computed(() => userStore.userInfo?.username || '未登录')
const initial = computed(() => (userStore.userInfo?.username || '?').charAt(0).toUpperCase())

const onCommand = (command) => {
  if (command !== 'logout') return
  userStore.logout()
  router.push('/login')
}

onMounted(() => {
  // 刷新页面后 store 里的 userInfo 会丢失，仅凭 token 补一次用户信息
  if (userStore.token && !userStore.userInfo) {
    userStore.fetchUserInfo().catch(() => {})
  }
})
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 20;
  background: var(--grad-brand);
  box-shadow: var(--shadow-md);
}

.app-header__inner {
  max-width: 1180px;
  margin: 0 auto;
  height: var(--header-h);
  padding: 0 20px;
  display: flex;
  align-items: center;
  gap: 20px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  flex-shrink: 0;
}

.brand__mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.28);
  color: #fff;
  backdrop-filter: blur(4px);
}

.brand__text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  color: #fff;
}

.brand__text strong {
  font-size: 15px;
  letter-spacing: 0.2px;
}

.brand__text small {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.78);
}

.nav {
  flex: 1;
  min-width: 0;
  --el-menu-text-color: rgba(255, 255, 255, 0.8);
  --el-menu-active-color: #fff;
  --el-menu-hover-bg-color: rgba(255, 255, 255, 0.12);
  --el-menu-bg-color: transparent;
  --el-menu-hover-text-color: #fff;
}

.nav :deep(.el-menu-item) {
  height: var(--header-h);
  font-size: 14px;
  border-bottom-width: 2px !important;
}

.nav :deep(.el-menu-item.is-active) {
  border-bottom-color: #fff !important;
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.icon-btn {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease;
}

.icon-btn:hover {
  background: rgba(255, 255, 255, 0.26);
  transform: translateY(-1px);
}

.user {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 10px 4px 4px;
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.28);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  outline: none;
  transition: background 0.2s ease;
}

.user:hover {
  background: rgba(255, 255, 255, 0.26);
}

.user__avatar {
  background: #fff;
  color: var(--brand-600);
  font-weight: 600;
}

.app-main {
  flex: 1;
  padding: 26px 20px 48px;
}

.app-main--bare {
  padding: 0;
}

@media (max-width: 860px) {
  .brand__text small {
    display: none;
  }

  .user__name {
    display: none;
  }
}

@media (max-width: 640px) {
  .app-header__inner {
    gap: 10px;
    padding: 0 12px;
  }

  .brand__text strong {
    font-size: 13px;
  }

  .nav :deep(.el-menu-item) {
    padding: 0 10px;
    font-size: 13px;
  }

  .app-main {
    padding: 18px 12px 36px;
  }
}
</style>
