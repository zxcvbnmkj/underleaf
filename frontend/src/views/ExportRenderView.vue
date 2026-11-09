<script setup lang="ts">
/**
 * PDF 导出渲染页：后端的无头 Chromium 打开此页并打印成 PDF（见 backend/app/services/pdf.py）。
 *
 * - 内容由后端在页面加载前注入：window.__UNDERLEAF_EXPORT__ = { title, content }，
 *   因此不需要登录，也不读取接口
 * - 用和编辑区预览、分享页相同的 MarkdownPreview 渲染，渲染效果改了 PDF 自动跟着变
 * - 固定浅色主题，打印样式见 markdown.css 中的 @page 和 @media print
 * - 渲染（含 Mermaid、字体、图片）全部完成后在 <html> 上标记 data-export-ready="true"，
 *   后端以此为准开始打印；没有注入内容时标记为 "error"
 */
import { computed, onMounted, ref } from 'vue'
import { NResult } from 'naive-ui'
import MarkdownPreview from '@/components/editor/MarkdownPreview.vue'
import { startsWithH1 } from '@/utils/markdown'

interface ExportPayload {
  title: string
  content: string
}

declare global {
  interface Window {
    __UNDERLEAF_EXPORT__?: ExportPayload
  }
}

const payload = ref<ExportPayload | null>(window.__UNDERLEAF_EXPORT__ ?? null)
const showTitle = computed(() => !!payload.value && !startsWithH1(payload.value.content))
let ready = false

function markReady(state: 'true' | 'error') {
  document.documentElement.dataset.exportReady = state
}

async function onRendered() {
  if (ready) return
  ready = true
  // 等字体和图片都加载完，否则 PDF 中可能出现回退字体或空白图片
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
  // 留一帧给浏览器完成布局
  requestAnimationFrame(() => markReady('true'))
}

onMounted(() => {
  // 打印固定为浅色，与当前界面主题无关
  document.documentElement.classList.remove('dark')
  if (payload.value) document.title = payload.value.title
  else markReady('error')
})
</script>

<template>
  <div class="export-page">
    <NResult
      v-if="!payload"
      status="info"
      title="PDF 导出渲染页"
      description="此页面供后端生成 PDF 使用，请在笔记页面点击「导出 → 导出 PDF」。"
      class="export-empty"
    />
    <article v-else class="export-article">
      <h1 v-if="showTitle" class="export-title">{{ payload.title }}</h1>
      <MarkdownPreview :source="payload.content" :dark="false" @rendered="onRendered" />
    </article>
  </div>
</template>

<style scoped>
.export-page {
  min-height: 100vh;
  background: var(--ul-bg);
}
/* 屏幕上按 A4 版心宽度显示（210mm - 左右页边距 2×18mm），便于调试排版 */
.export-article {
  width: min(174mm, calc(100% - 32px));
  margin: 0 auto;
  padding: 24px 0;
}
.export-title {
  margin: 0 0 0.6em;
  font-size: 2em;
  line-height: 1.3;
}
.export-empty {
  padding-top: 15vh;
}

@media print {
  .export-article {
    width: auto;
    padding: 0;
  }
}
</style>
