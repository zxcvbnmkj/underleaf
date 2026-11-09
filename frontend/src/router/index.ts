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
      // PDF 导出渲染页：由后端无头 Chromium 打开，内容由后端注入，不需要登录
      path: '/export/render',
      name: 'export-render',
      component: () => import('@/views/ExportRenderView.vue'),
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
