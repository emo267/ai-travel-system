import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('../views/Login.vue') },
  { path: '/', redirect: '/travel/list' },
  { path: '/travel/create', component: () => import('../views/TravelCreate.vue') },
  { path: '/travel/list', component: () => import('../views/TravelList.vue') },
  { path: '/travel/detail/:id', component: () => import('../views/TravelDetail.vue') },
  { path: '/chat', component: () => import('../views/ChatAssistant.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫：未登录跳转登录页
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.path !== '/login' && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router