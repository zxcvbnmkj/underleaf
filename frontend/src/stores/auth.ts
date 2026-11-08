import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/http'
import type { User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  /** 是否已向后端确认过登录状态 */
  let checked: Promise<void> | null = null

  /** 登录态保存在 httpOnly Cookie 中，前端只能通过 /auth/me 判断是否已登录 */
  function ensureChecked() {
    checked ??= authApi
      .me()
      .then((u) => {
        user.value = u
      })
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 401)) console.error(e)
        user.value = null
      })
    return checked
  }

  function setUser(u: User | null) {
    user.value = u
    checked = Promise.resolve()
  }

  async function logout() {
    await authApi.logout().catch(() => undefined)
    setUser(null)
  }

  return { user, ensureChecked, setUser, logout }
})
