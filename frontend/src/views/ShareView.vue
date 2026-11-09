<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NDrawer, NDrawerContent, NIcon, NResult, NSpin } from 'naive-ui'
import { Moon, Sun, TableOfContents } from 'lucide-vue-next'
import MarkdownPreview from '@/components/editor/MarkdownPreview.vue'
import BrandLogo from '@/components/common/BrandLogo.vue'
import OutlinePanel from '@/components/editor/OutlinePanel.vue'
import { getMarkdown } from '@/markdown'
import { extractOutline, type OutlineItem } from '@/markdown/outline'
import { useMediaQuery } from '@/composables/useMediaQuery'
import { notesApi } from '@/api/notes'
import { ApiError } from '@/api/http'
import { useTheme } from '@/composables/useTheme'
import { formatDateTime } from '@/utils/format'
import { startsWithH1 } from '@/utils/markdown'
import type { SharedNote } from '@/types'

const route = useRoute()
const { isDark, toggle: toggleTheme } = useTheme()

const note = ref<SharedNote | null>(null)
const error = ref<'not_found' | 'failed' | null>(null)
const loading = ref(true)
/** 正文以一级标题开头时不再单独显示标题，避免重复 */
const contentHasTitle = computed(() => startsWithH1(note.value?.content ?? ''))
/** 头像显示昵称的第一个字（中文昵称取一个汉字，英文取大写首字母） */
const authorInitial = computed(() =>
  Array.from(note.value?.author.nickname ?? '?')[0]!.toUpperCase(),
)

// ---------- 目录 ----------
/** 顶部导航栏高度：跳转和判断当前章节时要避开它 */
const HEADER_HEIGHT = 52
/** 宽屏时目录固定在正文右侧，否则通过右下角按钮打开抽屉 */
const wide = useMediaQuery('(min-width: 1180px)')
const drawerOpen = ref(false)
const outline = ref<OutlineItem[]>([])
const visibleLine = ref(-1)
const article = ref<HTMLElement>()

watch(note, async (n) => {
  outline.value = n ? extractOutline(await getMarkdown(), n.content) : []
  updateVisibleLine()
})

const headingAt = (line: number) =>
  article.value?.querySelector<HTMLElement>(`.markdown-body [data-line="${line}"]`)

/** 当前章节：最后一个滚过顶部导航栏的标题；还没滚到任何标题时为第一个标题 */
function updateVisibleLine() {
  let line = outline.value[0]?.line ?? -1
  for (const item of outline.value) {
    const el = headingAt(item.line)
    if (el && el.getBoundingClientRect().top <= HEADER_HEIGHT + 24) line = item.line
  }
  visibleLine.value = line
}
let frame = 0
const onScroll = () => {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(updateVisibleLine)
}
onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  cancelAnimationFrame(frame)
})

function onOutlineSelect(item: OutlineItem) {
  drawerOpen.value = false
  const el = headingAt(item.line)
  if (!el) return
  const top = el.getBoundingClientRect().top + window.scrollY - HEADER_HEIGHT - 16
  window.scrollTo({ top, behavior: 'smooth' })
  el.classList.remove('outline-flash')
  void el.offsetWidth // 重新触发动画
  el.classList.add('outline-flash')
  setTimeout(() => el.classList.remove('outline-flash'), 1500)
}

async function load() {
  loading.value = true
  error.value = null
  try {
    note.value = await notesApi.getShared(String(route.params.publicId))
    document.title = `${note.value.title} - Underleaf`
  } catch (e) {
    error.value = e instanceof ApiError && e.status === 404 ? 'not_found' : 'failed'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="share-page">
    <header class="share-header">
      <RouterLink to="/" class="logo-link"><BrandLogo /></RouterLink>
      <button
        class="theme-toggle"
        :aria-label="isDark ? '浅色模式' : '深色模式'"
        @click="toggleTheme"
      >
        <NIcon :size="18"><Sun v-if="isDark" /><Moon v-else /></NIcon>
      </button>
    </header>

    <main class="share-main" :class="{ 'with-outline': wide && outline.length }">
      <NSpin v-if="loading" class="share-loading" />
      <NResult
        v-else-if="error === 'not_found'"
        status="404"
        title="分享不存在或已关闭"
        description="链接可能有误，或者作者已经关闭了这篇笔记的公开分享。"
      />
      <NResult v-else-if="error" status="error" title="加载失败" description="请检查网络后重试。">
        <template #footer><NButton @click="load">重试</NButton></template>
      </NResult>
      <article v-else-if="note" ref="article">
        <h1 v-if="!contentHasTitle" class="share-title">{{ note.title }}</h1>
        <div class="share-meta">
          <span class="meta-author">
            <span class="author-avatar" aria-hidden="true">{{ authorInitial }}</span>
            <span class="author-name">{{ note.author.nickname }}</span>
          </span>
          <span class="meta-sep meta-sep-author">·</span>
          <span class="meta-times">
            <span>创建于 {{ formatDateTime(note.createdAt) }}</span>
            <span class="meta-sep">·</span>
            <span>更新于 {{ formatDateTime(note.updatedAt) }}</span>
          </span>
        </div>
        <MarkdownPreview :source="note.content" :dark="isDark" @rendered="updateVisibleLine" />
      </article>
      <aside v-if="note && wide && outline.length" class="share-outline">
        <OutlinePanel :items="outline" :visible-line="visibleLine" @select="onOutlineSelect" />
      </aside>
    </main>

    <template v-if="note && !wide && outline.length">
      <button type="button" class="outline-fab" aria-label="目录" @click="drawerOpen = true">
        <NIcon :size="18"><TableOfContents /></NIcon>
        <span>目录</span>
      </button>
      <NDrawer v-model:show="drawerOpen" placement="right" :width="280">
        <NDrawerContent body-content-style="padding: 0">
          <OutlinePanel :items="outline" :visible-line="visibleLine" @select="onOutlineSelect" />
        </NDrawerContent>
      </NDrawer>
    </template>

    <footer v-if="note" class="share-footer">
      由 <RouterLink to="/">Underleaf</RouterLink> 分享
    </footer>
  </div>
</template>

<style scoped>
.share-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--ul-bg);
}
.share-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 52px;
  padding: 0 20px;
  border-bottom: 1px solid var(--ul-border);
  background: color-mix(in srgb, var(--ul-bg) 85%, transparent);
  backdrop-filter: blur(8px);
}
.logo-link {
  text-decoration: none;
}
.theme-toggle {
  display: inline-flex;
  padding: 8px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--ul-text-2);
  cursor: pointer;
}
.theme-toggle:hover {
  background: var(--ul-bg-mute);
}
.share-main {
  flex: 1;
  width: min(820px, 100%);
  margin: 0 auto;
  padding: 40px 16px 64px;
}
/* 宽屏：正文 + 右侧目录，整体居中 */
.share-main.with-outline {
  display: grid;
  grid-template-columns: minmax(0, 820px) 220px;
  gap: 48px;
  width: min(1140px, 100%);
}
.share-main.with-outline > article {
  min-width: 0;
}
.share-outline {
  position: sticky;
  top: 76px;
  align-self: start;
  max-height: calc(100vh - 100px);
  overflow-y: auto; /* 标题很多时目录自身滚动 */
  border-left: 1px solid var(--ul-border);
}
.outline-fab {
  position: fixed;
  right: 16px;
  bottom: 20px;
  z-index: 20;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--ul-border);
  border-radius: 999px;
  background: var(--ul-bg);
  box-shadow: 0 2px 10px rgb(0 0 0 / 0.12);
  color: var(--ul-text-2);
  font-size: 13px;
  cursor: pointer;
}
.outline-fab:hover {
  color: var(--ul-accent);
}
@media print {
  .share-outline,
  .outline-fab {
    display: none;
  }
}
.share-loading {
  display: flex;
  justify-content: center;
  margin-top: 20vh;
}
.share-title {
  margin: 0 0 8px;
  font-size: 2.1em;
  line-height: 1.3;
}
.share-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0 0 32px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--ul-border);
  font-size: 13px;
  color: var(--ul-text-3);
}
.meta-author,
.meta-times {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
/* 窄屏：作者一行，时间一行 */
@media (max-width: 560px) {
  .meta-times {
    flex-basis: 100%;
  }
  .meta-sep-author {
    display: none;
  }
}
.author-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--ul-accent);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.author-name {
  font-weight: 500;
  color: var(--ul-text-2);
}
.meta-sep {
  color: var(--ul-text-3);
}
.share-footer {
  padding: 24px 16px 32px;
  text-align: center;
  font-size: 12px;
  color: var(--ul-text-3);
}
.share-footer a {
  color: var(--ul-accent);
  text-decoration: none;
}
</style>
