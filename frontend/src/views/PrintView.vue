<script setup lang="ts">
/**
 * 打印页：PDF 导出的唯一排版来源。
 *
 * - 用和编辑区预览、分享页相同的 MarkdownPreview 渲染，渲染效果改了这里自动跟着变
 * - 固定使用浅色主题，打印样式见 markdown.css 中的 @media print
 * - 渲染（含 Mermaid、字体）全部完成后在 <html> 上标记 data-export-ready，
 *   浏览器打印和后端 Playwright 都以此为准，避免打出半成品
 * - ?auto=1 时自动弹出打印对话框，打印结束后关闭标签页
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NResult, NSpin } from 'naive-ui'
import MarkdownPreview from '@/components/editor/MarkdownPreview.vue'
import { notesApi } from '@/api/notes'
import { ApiError } from '@/api/http'
import { startsWithH1 } from '@/utils/markdown'
import type { Note } from '@/types'

const route = useRoute()
const auto = route.query.auto === '1'

const note = ref<Note | null>(null)
const error = ref<string | null>(null)
const ready = ref(false)
const showTitle = computed(() => !!note.value && !startsWithH1(note.value.content))

function markReady(state: 'true' | 'error') {
  document.documentElement.dataset.exportReady = state
}

async function onRendered() {
  if (ready.value) return
  // 等字体和图片都加载完，否则打印时可能出现回退字体或空白图片
  await document.fonts.ready
  await Promise.all(
    Array.from(document.images)
      .filter((img) => !img.complete)
      .map(
        (img) =>
          new Promise((r) => {
            img.addEventListener('load', r, { once: true })
            img.addEventListener('error', r, { once: true })
          }),
      ),
  )
  ready.value = true
  markReady('true')
  if (auto) {
    window.addEventListener('afterprint', () => window.close(), { once: true })
    // 留一帧给浏览器完成布局
    requestAnimationFrame(print)
  }
}

function print() {
  window.print()
}

onMounted(async () => {
  // 打印固定为浅色，与当前界面主题无关
  document.documentElement.classList.remove('dark')
  try {
    note.value = await notesApi.get(Number(route.params.noteId))
    document.title = note.value.title // 浏览器“另存为 PDF”默认用它作文件名
  } catch (e) {
    error.value = e instanceof ApiError && e.status === 404 ? '笔记不存在' : '加载失败'
    markReady('error')
  }
})
</script>

<template>
  <div class="print-page">
    <div class="print-toolbar">
      <span>{{ ready ? '在打印对话框中选择“另存为 PDF”即可导出' : '正在准备导出…' }}</span>
      <NButton size="small" type="primary" :disabled="!ready" @click="print">
        打印 / 保存为 PDF
      </NButton>
    </div>

    <NResult v-if="error" status="404" :title="error" class="print-error" />
    <NSpin v-else-if="!note" class="print-loading" />
    <article v-else class="print-article">
      <h1 v-if="showTitle" class="print-title">{{ note.title }}</h1>
      <MarkdownPreview :source="note.content" :dark="false" @rendered="onRendered" />
    </article>
  </div>
</template>

<style scoped>
.print-page {
  min-height: 100vh;
  background: var(--ul-bg-soft);
}
.print-toolbar {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--ul-border);
  background: var(--ul-bg);
  font-size: 13px;
  color: var(--ul-text-2);
}
/* 屏幕上模拟 A4 纸张宽度（210mm - 左右页边距 2×18mm） */
.print-article {
  box-sizing: content-box;
  width: min(174mm, calc(100% - 32px));
  margin: 24px auto;
  padding: 16mm 18mm;
  background: var(--ul-bg);
  box-shadow: 0 1px 4px rgb(0 0 0 / 0.08);
}
.print-title {
  margin: 0 0 0.6em;
  font-size: 2em;
  line-height: 1.3;
}
.print-loading {
  display: flex;
  justify-content: center;
  padding-top: 20vh;
}
.print-error {
  padding-top: 15vh;
}

@media (max-width: 640px) {
  .print-article {
    padding: 20px 16px;
  }
}

@media print {
  .print-page {
    min-height: 0;
    background: none;
  }
  .print-toolbar {
    display: none;
  }
  .print-article {
    width: auto;
    margin: 0;
    padding: 0;
    box-shadow: none;
  }
}
</style>
