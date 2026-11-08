<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NDrawer, NDropdown, NEmpty, NIcon, NTag, NTooltip, useMessage } from 'naive-ui'
import {
  FilePlus,
  FileText,
  KeyRound,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeft,
  Sun,
} from 'lucide-vue-next'
import FolderTree from '@/components/sidebar/FolderTree.vue'
import NoteWorkspace from '@/components/editor/NoteWorkspace.vue'
import PasswordModal from '@/components/common/PasswordModal.vue'
import BrandLogo from '@/components/common/BrandLogo.vue'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import { useTheme } from '@/composables/useTheme'
import { useMediaQuery } from '@/composables/useMediaQuery'
import { USE_MOCK } from '@/api/http'
import { formatRelative } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()
const store = useWorkspaceStore()
const { isDark, toggle: toggleTheme } = useTheme()
const narrow = useMediaQuery('(max-width: 767px)')

const noteId = computed(() => {
  const id = route.params.noteId
  return typeof id === 'string' && id ? Number(id) : null
})

// ---------- 侧边栏 ----------
const SIDEBAR_KEY = 'underleaf-sidebar'
const sidebarOpen = ref(readSidebar())
const drawerOpen = ref(false)
function readSidebar() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) !== 'closed'
  } catch {
    return true
  }
}
function toggleSidebar() {
  if (narrow.value) {
    drawerOpen.value = !drawerOpen.value
    return
  }
  sidebarOpen.value = !sidebarOpen.value
  try {
    localStorage.setItem(SIDEBAR_KEY, sidebarOpen.value ? 'open' : 'closed')
  } catch {
    /* ignore */
  }
}
watch(narrow, () => (drawerOpen.value = false))

onMounted(async () => {
  try {
    await store.load()
  } catch (e) {
    message.error(`加载笔记列表失败：${(e as Error).message}`)
  }
})

// ---------- 用户菜单 ----------
const showPassword = ref(false)
const userMenu = computed(() => [
  {
    key: 'email',
    type: 'render',
    render: () => h('div', { class: 'user-menu-email' }, auth.user?.email),
  },
  { type: 'divider', key: 'd' },
  {
    label: auth.user?.hasPassword ? '修改密码' : '设置密码',
    key: 'password',
    icon: () => h(NIcon, null, () => h(KeyRound)),
  },
  { label: '退出登录', key: 'logout', icon: () => h(NIcon, null, () => h(LogOut)) },
])
async function onUserMenu(key: string) {
  if (key === 'password') showPassword.value = true
  if (key === 'logout') {
    await auth.logout()
    store.reset()
    router.replace({ name: 'login' })
  }
}
const avatar = computed(() => (auth.user?.email[0] ?? '?').toUpperCase())

// ---------- 空状态 ----------
const recent = computed(() =>
  [...store.notes].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).slice(0, 6),
)
async function newNote() {
  try {
    const note = await store.createNote(null)
    router.push({ name: 'workspace', params: { noteId: note.id } })
  } catch (e) {
    message.error((e as Error).message)
  }
}
</script>

<template>
  <div class="workspace">
    <header class="app-header">
      <NTooltip>
        <template #trigger>
          <NButton quaternary circle size="small" aria-label="切换侧边栏" @click="toggleSidebar">
            <template #icon>
              <NIcon>
                <Menu v-if="narrow" />
                <PanelLeftClose v-else-if="sidebarOpen" />
                <PanelLeft v-else />
              </NIcon>
            </template>
          </NButton>
        </template>
        {{ sidebarOpen ? '收起侧边栏' : '展开侧边栏' }}
      </NTooltip>
      <RouterLink to="/notes" class="logo-link"><BrandLogo /></RouterLink>
      <NTooltip v-if="USE_MOCK">
        <template #trigger>
          <NTag size="small" round :bordered="false" type="warning">演示模式</NTag>
        </template>
        未连接后端，数据保存在当前浏览器中
      </NTooltip>
      <div class="header-spacer" />
      <NTooltip>
        <template #trigger>
          <NButton quaternary circle size="small" aria-label="切换主题" @click="toggleTheme">
            <template #icon>
              <NIcon><Sun v-if="isDark" /><Moon v-else /></NIcon>
            </template>
          </NButton>
        </template>
        {{ isDark ? '浅色模式' : '深色模式' }}
      </NTooltip>
      <NDropdown :options="userMenu" trigger="click" placement="bottom-end" @select="onUserMenu">
        <button class="avatar" :aria-label="`账户：${auth.user?.email}`">{{ avatar }}</button>
      </NDropdown>
    </header>

    <div class="workspace-body">
      <aside v-if="!narrow" v-show="sidebarOpen" class="sidebar">
        <FolderTree :current-note-id="noteId" />
      </aside>
      <NDrawer v-else v-model:show="drawerOpen" placement="left" :width="290">
        <div class="drawer-tree">
          <FolderTree :current-note-id="noteId" @navigate="drawerOpen = false" />
        </div>
      </NDrawer>

      <main class="main">
        <NoteWorkspace v-if="noteId != null" :note-id="noteId" :dark="isDark" :narrow="narrow" />
        <div v-else class="empty-state">
          <NEmpty description="从左侧选择一篇笔记，或者新建一篇">
            <template #extra>
              <NButton type="primary" @click="newNote">
                <template #icon
                  ><NIcon><FilePlus /></NIcon
                ></template>
                新建笔记
              </NButton>
            </template>
          </NEmpty>
          <section v-if="recent.length" class="recent">
            <h3>最近编辑</h3>
            <RouterLink
              v-for="n in recent"
              :key="n.id"
              class="recent-item"
              :to="{ name: 'workspace', params: { noteId: n.id } }"
            >
              <NIcon :size="16" class="recent-icon"><FileText /></NIcon>
              <span class="recent-title">{{ n.title }}</span>
              <span class="recent-time">{{ formatRelative(n.updatedAt) }}</span>
            </RouterLink>
          </section>
        </div>
      </main>
    </div>

    <PasswordModal v-model:show="showPassword" />
  </div>
</template>

<style scoped>
.workspace {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
}
.app-header {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 48px;
  flex-shrink: 0;
  padding: 0 12px;
  border-bottom: 1px solid var(--ul-border);
  background: var(--ul-bg-soft);
}
.logo-link {
  text-decoration: none;
}
.header-spacer {
  flex: 1;
}
.avatar {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  background: var(--ul-accent);
  color: #fff;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}
.workspace-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.sidebar {
  width: 264px;
  flex-shrink: 0;
  border-right: 1px solid var(--ul-border);
  background: var(--ul-bg-soft);
}
.drawer-tree {
  height: 100%;
  background: var(--ul-bg-soft);
}
.main {
  flex: 1;
  min-width: 0;
  background: var(--ul-bg);
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 14vh 16px 32px;
  gap: 40px;
}
.recent {
  width: min(440px, 100%);
}
.recent h3 {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ul-text-2);
}
.recent-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  color: var(--ul-text);
  text-decoration: none;
}
.recent-item:hover {
  background: var(--ul-bg-mute);
}
.recent-icon {
  color: var(--ul-text-3);
}
.recent-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-time {
  font-size: 12px;
  color: var(--ul-text-3);
}
:global(.user-menu-email) {
  padding: 6px 14px 4px;
  font-size: 12px;
  color: var(--ul-text-2);
}
</style>
