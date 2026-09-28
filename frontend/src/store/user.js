import { defineStore } from 'pinia'
import { login, getUserInfo } from '../api/auth'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('access_token') || '',
    userInfo: null,
  }),
  actions: {
    async loginAction(loginData) {
      const res = await login(loginData)
      this.token = res.access_token
      localStorage.setItem('access_token', res.access_token)
      await this.fetchUserInfo()
    },
    async fetchUserInfo() {
      this.userInfo = await getUserInfo()
    },
    logout() {
      this.token = ''
      this.userInfo = null
      localStorage.removeItem('access_token')
    }
  }
})