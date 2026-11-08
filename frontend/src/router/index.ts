import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/notes' },
    {
      path: '/notes/:noteId(\\d+)?',
      name: 'workspace',
      component: () => import('@/views/WorkspaceView.vue'),
      meta: { requiresAuth: true },
    },
    {
      // PDF 导出的打印页（浏览器打印和后端 Playwright 共用）
      path: '/print/:noteId(\\d+)',
      name: 'print',
      component: () => import('@/views/PrintView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guestOnly: true },
    },
    {
      path: '/s/:publicId',
      name: 'share',
      component: () => import('@/views/ShareView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  if (!to.meta.requiresAuth && !to.meta.guestOnly) return true
  const auth = useAuthStore()
  await auth.ensureChecked()
  if (to.meta.requiresAuth && !auth.user) {
    return { name: 'login', query: to.fullPath === '/notes' ? {} : { redirect: to.fullPath } }
  }
  if (to.meta.guestOnly && auth.user) return { path: '/notes' }
  return true
})

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    guestOnly?: boolean
  }
}

export default router
