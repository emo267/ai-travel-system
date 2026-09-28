<template>
  <div class="login">
    <aside class="login__brand" :style="brandStyle">
      <div class="brand-top">
        <span class="brand-mark">
          <el-icon :size="20"><Promotion /></el-icon>
        </span>
        <span class="brand-name">旅行计划智能助手</span>
      </div>

      <div class="brand-body">
        <h1>把行程交给 AI，<br />把时间留给风景</h1>
        <p>说清楚去哪、几天、预算多少，剩下的交给它。</p>
        <ul class="features">
          <li v-for="f in features" :key="f.title">
            <span class="features__icon">
              <el-icon :size="16"><component :is="f.icon" /></el-icon>
            </span>
            <span>
              <strong>{{ f.title }}</strong>
              <small>{{ f.desc }}</small>
            </span>
          </li>
        </ul>
      </div>

      <p class="brand-foot">DeepSeek 生成 · RAG 知识库 · 高德地图可视化</p>
    </aside>

    <section class="login__form">
      <button class="theme-btn" type="button" @click="toggleTheme">
        <el-icon :size="17">
          <Sunny v-if="isDark" />
          <Moon v-else />
        </el-icon>
      </button>

      <div class="form-card">
        <h2>{{ isRegister ? '创建账号' : '欢迎回来' }}</h2>
        <p class="form-sub">
          {{ isRegister ? '注册后即可生成你的第一份行程' : '登录后继续管理你的行程计划' }}
        </p>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          size="large"
          @keyup.enter="submit"
        >
          <el-form-item prop="username" label="用户名">
            <el-input v-model="form.username" placeholder="请输入用户名" :prefix-icon="User" clearable />
          </el-form-item>

          <el-form-item prop="password" label="密码">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              :prefix-icon="Lock"
              show-password
            />
          </el-form-item>

          <el-button type="primary" class="submit" :loading="loading" @click="submit">
            {{ isRegister ? '注册' : '登录' }}
          </el-button>
        </el-form>

        <div class="toggle">
          <span>{{ isRegister ? '已经有账号了？' : '还没有账号？' }}</span>
          <a @click="switchMode">{{ isRegister ? '去登录' : '立即注册' }}</a>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Lock, Moon, Promotion, Sunny, MapLocation, User, Wallet } from '@element-plus/icons-vue'
import { useUserStore } from '../store/user'
import { useTheme } from '../utils/theme'
import { register } from '../api/auth'

const loginBgModules = import.meta.glob('../assets/images/login-bg.{jpg,jpeg,png,webp}', {
  eager: true,
})

const router = useRouter()
const userStore = useUserStore()
const { isDark, toggleTheme } = useTheme()

const formRef = ref(null)
const isRegister = ref(false)
const loading = ref(false)
const form = ref({ username: '', password: '' })

const features = [
  { icon: MapLocation, title: '逐日行程规划', desc: '景点、餐饮、住宿、交通一次给全' },
  { icon: Wallet, title: '预算自动核算', desc: '对比预算给出超支提醒' },
  { icon: ChatDotRound, title: '边问边改', desc: '就着这份行程继续追问细节' },
]

const bgStyle = computed(() => {
  const bg = Object.values(loginBgModules)[0]?.default
  return bg ? { backgroundImage: `url(${bg})` } : {}
})

const brandStyle = computed(() => {
  const bg = Object.values(loginBgModules)[0]?.default
  return bg ? { backgroundImage: `url(${bg})` } : {}
})

// 登录侧不校验长度：后端登录接口对密码无长度约束，加限制会把历史短密码账号挡在门外
const rules = computed(() => ({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    ...(isRegister.value
      ? [{ min: 3, max: 50, message: '用户名长度 3-50 个字符', trigger: 'blur' }]
      : []),
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    ...(isRegister.value
      ? [{ min: 6, max: 100, message: '密码长度 6-100 个字符', trigger: 'blur' }]
      : []),
  ],
}))

const switchMode = () => {
  isRegister.value = !isRegister.value
  formRef.value?.clearValidate()
}

const submit = async () => {
  if (loading.value) return
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    if (isRegister.value) {
      await register(form.value)
      ElMessage.success('注册成功，请使用该账号登录')
      isRegister.value = false
      formRef.value?.clearValidate()
    } else {
      await userStore.loginAction(form.value)
      ElMessage.success(`欢迎回来，${form.value.username}`)
      router.push('/travel/list')
    }
  } catch {
    // 失败提示由 axios 响应拦截器统一弹出
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 1.05fr 1fr;
}

.login__brand {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 40px 44px;
  background: var(--grad-brand);
  background-size: cover;
  background-position: center;
  color: #fff;
  overflow: hidden;
}

.login__brand::after {
  content: '';
  position: absolute;
  right: -120px;
  bottom: -140px;
  width: 380px;
  height: 380px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
}

.brand-top {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  letter-spacing: 0.3px;
  text-shadow: 0 1px 8px rgba(8, 12, 24, 0.55);
}

.brand-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: rgba(10, 14, 26, 0.38);
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.brand-body {
  position: relative;
  z-index: 1;
  max-width: 420px;
}

.brand-body h1 {
  color: #fff;
  font-size: 32px;
  line-height: 1.4;
  letter-spacing: -0.5px;
  text-shadow: 0 2px 14px rgba(8, 12, 24, 0.55);
}

.brand-body > p {
  margin: 14px 0 26px;
  color: rgba(255, 255, 255, 0.92);
  font-size: 14px;
  text-shadow: 0 1px 8px rgba(8, 12, 24, 0.6);
}

.features {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 14px;
}

.features li {
  display: flex;
  align-items: flex-start;
  gap: 11px;
}

.features__icon {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: rgba(10, 14, 26, 0.38);
  border: 1px solid rgba(255, 255, 255, 0.28);
}

.features strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
  text-shadow: 0 1px 8px rgba(8, 12, 24, 0.55);
}

.features small {
  color: rgba(255, 255, 255, 0.85);
  font-size: 12.5px;
  text-shadow: 0 1px 8px rgba(8, 12, 24, 0.6);
}

.brand-foot {
  position: relative;
  z-index: 1;
  margin: 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
  text-shadow: 0 1px 8px rgba(8, 12, 24, 0.6);
}

.login__form {
  position: relative;
  display: grid;
  place-items: center;
  padding: 40px 24px;
  background: var(--bg);
}

.theme-btn {
  position: absolute;
  top: 20px;
  right: 22px;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid var(--border-1);
  background: var(--card);
  color: var(--text-2);
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.theme-btn:hover {
  color: var(--brand-600);
  border-color: var(--brand-400);
  transform: translateY(-1px);
}

.form-card {
  width: min(400px, 100%);
  padding: 36px 32px;
  border-radius: 18px;
  background: var(--card);
  border: 1px solid var(--border-1);
  box-shadow: 0 20px 50px rgba(8, 12, 24, 0.28);
}

.form-card h2 {
  font-size: 26px;
  letter-spacing: -0.4px;
}

.form-sub {
  margin: 8px 0 26px;
  color: var(--text-3);
  font-size: 13px;
}

.submit {
  width: 100%;
  height: 42px;
  font-size: 15px;
  letter-spacing: 1px;
  background: var(--grad-brand);
  border: none;
  box-shadow: var(--shadow-md);
}

.submit:hover {
  opacity: 0.94;
}

.toggle {
  margin-top: 18px;
  text-align: center;
  font-size: 13px;
  color: var(--text-3);
}

.toggle a {
  margin-left: 4px;
  color: var(--brand-600);
  cursor: pointer;
  font-weight: 600;
}

.toggle a:hover {
  text-decoration: underline;
}

@media (max-width: 900px) {
  .login {
    grid-template-columns: 1fr;
  }

  .login__brand {
    padding: 28px 24px 32px;
  }

  .brand-body h1 {
    font-size: 24px;
  }

  .features,
  .brand-foot {
    display: none;
  }

  .login__form {
    padding: 32px 20px 48px;
  }
}
</style>
