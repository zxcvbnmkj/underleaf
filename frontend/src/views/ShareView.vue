<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NIcon, NResult, NSpin } from 'naive-ui'
import { Moon, Sun } from 'lucide-vue-next'
import MarkdownPreview from '@/components/editor/MarkdownPreview.vue'
import BrandLogo from '@/components/common/BrandLogo.vue'
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

    <main class="share-main">
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
      <article v-else-if="note">
        <h1 v-if="!contentHasTitle" class="share-title">{{ note.title }}</h1>
        <p class="share-meta">更新于 {{ formatDateTime(note.updatedAt) }} · 只读</p>
        <MarkdownPreview :source="note.content" :dark="isDark" />
      </article>
    </main>

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
  margin: 0 0 32px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--ul-border);
  font-size: 13px;
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
