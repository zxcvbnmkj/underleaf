<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NDrawer, NDropdown, NIcon, NTooltip, useMessage } from 'naive-ui'
import {
  FilePlus,
  Folder,
  Globe,
  GitBranch,
  KeyRound,
  UserPen,
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
import GitSyncModal from '@/components/common/GitSyncModal.vue'
import BrandLogo from '@/components/common/BrandLogo.vue'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import { usePrompt } from '@/composables/usePrompt'
import { useWorkspaceStore } from '@/stores/workspace'
import { useTheme } from '@/composables/useTheme'
import { useMediaQuery } from '@/composables/useMediaQuery'
import { formatRelative } from '@/utils/format'
import { notesApi } from '@/api/notes'
import type { RecentNote } from '@/types'

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
const showGit = ref(false)
const prompt = usePrompt()
const userMenu = computed(() => [
  {
    key: 'profile',
    type: 'render',
    render: () =>
      h('div', { class: 'user-menu-profile' }, [
        h('div', { class: 'user-menu-nickname' }, auth.user?.nickname),
        h('div', { class: 'user-menu-email' }, auth.user?.email),
      ]),
  },
  { type: 'divider', key: 'd' },
  { label: '修改昵称', key: 'nickname', icon: () => h(NIcon, null, () => h(UserPen)) },
  { label: '修改密码', key: 'password', icon: () => h(NIcon, null, () => h(KeyRound)) },
  { label: 'Git 同步', key: 'git', icon: () => h(NIcon, null, () => h(GitBranch)) },
  { label: '退出登录', key: 'logout', icon: () => h(NIcon, null, () => h(LogOut)) },
])
async function changeNickname() {
  const nickname = await prompt({
    title: '修改昵称',
    value: auth.user?.nickname,
    placeholder: '2～20 个字符：中文、字母、数字、_ 或 -',
  })
  if (!nickname || nickname === auth.user?.nickname) return
  try {
    auth.setUser(await authApi.updateNickname(nickname))
    message.success('昵称已修改，之后可以用新昵称登录')
  } catch (e) {
    message.error((e as Error).message)
  }
}
async function onUserMenu(key: string) {
  if (key === 'nickname') void changeNickname()
  if (key === 'password') showPassword.value = true
  if (key === 'git') showGit.value = true
  if (key === 'logout') {
    await auth.logout()
    store.reset()
    router.replace({ name: 'login' })
  }
}
/** 头像显示昵称的第一个字（中文取一个汉字，英文取大写首字母） */
const avatar = computed(() => (Array.from(auth.user?.nickname ?? '?')[0] ?? '?').toUpperCase())

// ---------- 空状态 ----------
// 摘要需要正文，由后端单独返回；回到首页、笔记增删时重新获取
// 宽屏一行 4 张，显示 3 行
const RECENT_LIMIT = 12
const recentNotes = ref<RecentNote[]>([])
async function loadRecent() {
  try {
    recentNotes.value = await notesApi.recent(RECENT_LIMIT)
  } catch {
    // 只影响首页卡片，不打扰用户
  }
}
watch(
  () => (noteId.value == null ? store.notes.length : -1),
  (n) => {
    if (n >= 0) void loadRecent()
  },
  { immediate: true },
)
const recent = computed(() =>
  recentNotes.value.flatMap((r) => {
    // 标题、位置以文件夹树中的为准（在其他地方改名、移动、删除后无需重新获取）
    const n = store.noteById(r.id)
    if (!n) return []
    // 所在文件夹路径，如「工作 / 周报」；根目录显示「我的笔记」
    const location =
      store
        .folderPath(n.folderId)
        .map((id) => store.folderById(id)?.name)
        .join(' / ') || '我的笔记'
    return [{ ...n, excerpt: r.excerpt, location }]
  }),
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
        <button class="avatar" :aria-label="`账户：${auth.user?.nickname}`">{{ avatar }}</button>
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
          <section class="recent">
            <div class="recent-head">
              <h3>{{ recent.length ? '最近编辑' : '还没有笔记' }}</h3>
              <NButton type="primary" @click="newNote">
                <template #icon
                  ><NIcon><FilePlus /></NIcon
                ></template>
                新建笔记
              </NButton>
            </div>
            <div v-if="recent.length" class="recent-grid">
              <RouterLink
                v-for="n in recent"
                :key="n.id"
                class="recent-card"
                :to="{ name: 'workspace', params: { noteId: n.id } }"
              >
                <div class="card-head">
                  <span class="card-title" :title="n.title">{{ n.title }}</span>
                  <span class="card-location" :title="n.location">
                    <NIcon :size="12"><Folder /></NIcon>
                    <span class="card-location-text">{{ n.location }}</span>
                  </span>
                </div>
                <div class="card-excerpt" :class="{ empty: !n.excerpt }">
                  {{ n.excerpt || '空白笔记' }}
                </div>
                <div class="card-foot">
                  <span>{{ formatRelative(n.updatedAt) }}</span>
                  <NIcon v-if="n.isPublic" :size="13" title="已公开分享"><Globe /></NIcon>
                </div>
              </RouterLink>
            </div>
          </section>
        </div>
      </main>
    </div>

    <PasswordModal v-model:show="showPassword" />
    <GitSyncModal v-model:show="showGit" />
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
  padding: 8vh 16px 32px;
}
.recent {
  width: min(1040px, 100%);
}
.recent-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.recent h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--ul-text-2);
}
.recent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}
.recent-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 180px;
  padding: 16px 18px;
  border: 1px solid var(--ul-border);
  border-radius: 10px;
  background: var(--ul-bg-soft);
  color: var(--ul-text);
  text-decoration: none;
  transition:
    border-color 0.15s,
    box-shadow 0.15s,
    transform 0.15s;
}
.recent-card:hover {
  border-color: var(--ul-accent);
  box-shadow: 0 4px 16px rgb(0 0 0 / 0.06);
  transform: translateY(-1px);
}
.recent-card:focus-visible {
  outline: 2px solid var(--ul-accent);
  outline-offset: 2px;
}
.card-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.card-title {
  flex: 1;
  min-width: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.45;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.card-excerpt {
  flex: 1;
  font-size: 13px;
  line-height: 1.6;
  color: var(--ul-text-2);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.card-excerpt.empty {
  color: var(--ul-text-3);
  font-style: italic;
}
.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--ul-text-3);
}
/* 所在文件夹：标题右侧，文件夹名较长时最多占 40% 宽度，优先保证标题完整 */
.card-location {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 1;
  min-width: 0;
  max-width: 40%;
  font-size: 12px;
  color: var(--ul-text-3);
  align-self: center;
}
.card-location-text {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
@media (max-width: 560px) {
  .recent-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
:global(.user-menu-profile) {
  padding: 6px 14px 4px;
  max-width: 240px;
}
:global(.user-menu-nickname) {
  font-size: 14px;
  font-weight: 600;
  color: var(--ul-text);
  overflow: hidden;
  text-overflow: ellipsis;
}
:global(.user-menu-email) {
  font-size: 12px;
  color: var(--ul-text-3);
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
