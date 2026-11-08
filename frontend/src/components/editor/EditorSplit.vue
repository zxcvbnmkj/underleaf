<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import MarkdownEditor from './MarkdownEditor.vue'
import MarkdownPreview from './MarkdownPreview.vue'
import { createScrollSync } from '@/composables/useScrollSync'

export type ViewMode = 'split' | 'edit' | 'preview'

const props = defineProps<{
  mode: ViewMode
  dark: boolean
  readonly?: boolean
}>()
const content = defineModel<string>({ required: true })
const emit = defineEmits<{ save: [] }>()

const RATIO_KEY = 'underleaf-split-ratio'
const ratio = ref(readRatio())
function readRatio() {
  try {
    const v = Number(localStorage.getItem(RATIO_KEY))
    if (v >= 0.2 && v <= 0.8) return v
  } catch {
    /* ignore */
  }
  return 0.5
}

const container = ref<HTMLDivElement>()
const previewPane = ref<HTMLDivElement>()
const editor = ref<InstanceType<typeof MarkdownEditor>>()

const totalLines = computed(() => content.value.split('\n').length)
const sync = createScrollSync(() => previewPane.value)

/** 当前由哪一侧主导滚动（鼠标所在或获得焦点的一侧），只同步这一侧的滚动，避免互相触发 */
let source: 'editor' | 'preview' = 'editor'
const setSource = (s: typeof source) => (source = s)

function onEditorScroll(line: number) {
  if (props.mode !== 'split' || source !== 'editor') return
  const pane = previewPane.value
  if (!pane) return
  const scroller = editor.value?.scrollDOM
  // 编辑区滚到底时预览区也滚到底
  const atBottom =
    scroller && scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2
  pane.scrollTop = atBottom ? pane.scrollHeight : sync.previewTopForLine(line, totalLines.value)
}

function onPreviewScroll() {
  if (props.mode !== 'split' || source !== 'preview') return
  const pane = previewPane.value
  if (!pane) return
  editor.value?.scrollToLine(sync.lineForPreviewTop(pane.scrollTop, totalLines.value))
}

// ---------- 拖拽分隔条 ----------
const dragging = ref(false)
function startDrag(e: PointerEvent) {
  dragging.value = true
  ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
}
function onDrag(e: PointerEvent) {
  if (!dragging.value || !container.value) return
  const rect = container.value.getBoundingClientRect()
  ratio.value = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0.2), 0.8)
}
function endDrag() {
  if (!dragging.value) return
  dragging.value = false
  sync.invalidate()
  try {
    localStorage.setItem(RATIO_KEY, String(ratio.value))
  } catch {
    /* ignore */
  }
}

let resizeObserver: ResizeObserver | null = null
onMounted(() => {
  resizeObserver = new ResizeObserver(() => sync.invalidate())
  if (previewPane.value) resizeObserver.observe(previewPane.value)
})
onBeforeUnmount(() => resizeObserver?.disconnect())

defineExpose({ focus: () => editor.value?.focus() })
</script>

<template>
  <div
    ref="container"
    class="editor-split"
    :class="[`mode-${mode}`, { dragging }]"
    :style="{ '--ratio': ratio }"
  >
    <div
      v-show="mode !== 'preview'"
      class="pane editor-pane"
      @mouseenter="setSource('editor')"
      @focusin="setSource('editor')"
    >
      <MarkdownEditor
        ref="editor"
        v-model="content"
        :dark="dark"
        :readonly="readonly"
        @scroll="onEditorScroll"
        @save="emit('save')"
      />
    </div>
    <div
      v-if="mode === 'split'"
      class="divider"
      role="separator"
      aria-orientation="vertical"
      @pointerdown="startDrag"
      @pointermove="onDrag"
      @pointerup="endDrag"
      @pointercancel="endDrag"
      @dblclick="ratio = 0.5"
    />
    <div
      v-show="mode !== 'edit'"
      ref="previewPane"
      class="pane preview-pane"
      @mouseenter="setSource('preview')"
      @scroll.passive="onPreviewScroll"
    >
      <MarkdownPreview :source="content" :dark="dark" @rendered="sync.invalidate()" />
    </div>
  </div>
</template>

<style scoped>
.editor-split {
  display: flex;
  height: 100%;
  min-height: 0;
}
.editor-split.dragging {
  cursor: col-resize;
  user-select: none;
}
.pane {
  min-width: 0;
  height: 100%;
}
.mode-split .editor-pane {
  flex: 0 0 calc(var(--ratio) * 100%);
}
.mode-split .preview-pane,
.mode-edit .editor-pane,
.mode-preview .preview-pane {
  flex: 1 1 0;
}
.preview-pane {
  overflow-y: auto;
  padding: 24px clamp(20px, 4vw, 48px) 40vh;
  background: var(--ul-bg);
}
.mode-preview .preview-pane :deep(.markdown-body) {
  max-width: 820px;
  margin: 0 auto;
}
.divider {
  flex: 0 0 5px;
  margin: 0 -2px;
  z-index: 1;
  cursor: col-resize;
  background: linear-gradient(var(--ul-border), var(--ul-border)) center / 1px 100% no-repeat;
  transition: background-color 0.15s;
}
.divider:hover,
.dragging .divider {
  background-color: var(--ul-accent-soft);
}
</style>
