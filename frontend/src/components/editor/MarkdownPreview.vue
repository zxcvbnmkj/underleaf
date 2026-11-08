<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { getMarkdown, renderMermaid } from '@/markdown'

const props = withDefaults(
  defineProps<{
    source: string
    dark: boolean
    /** 输入时的渲染防抖（毫秒） */
    debounce?: number
  }>(),
  { debounce: 120 },
)

const emit = defineEmits<{ rendered: [] }>()

const root = ref<HTMLDivElement>()
const html = ref('')
const ready = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

async function render() {
  const md = await getMarkdown()
  html.value = md.render(props.source)
  ready.value = true
  await nextTick()
  if (root.value) await renderMermaid(root.value, props.dark)
  emit('rendered')
}

onMounted(render)

watch(
  () => props.source,
  () => {
    clearTimeout(timer)
    timer = setTimeout(render, props.debounce)
  },
)

// 切换主题时重新渲染 mermaid 图表
watch(
  () => props.dark,
  async () => {
    if (!root.value) return
    root.value.querySelectorAll<HTMLElement>('pre.mermaid[data-done]').forEach((el) => {
      delete el.dataset.done
      el.textContent = el.dataset.source ?? ''
    })
    await renderMermaid(root.value, props.dark)
  },
)

defineExpose({ el: root })
</script>

<template>
  <div ref="root" class="markdown-body">
    <div v-if="!ready" class="preview-loading">渲染中…</div>
    <!-- markdown-it 已禁用原始 HTML，输出内容是安全的 -->
    <div v-else v-html="html" />
  </div>
</template>

<style scoped>
.preview-loading {
  color: var(--ul-text-3);
  font-size: 14px;
}
</style>
