<script setup lang="ts">
import { computed, h, nextTick, ref, toRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NDropdown,
  NIcon,
  NInput,
  NResult,
  NSpin,
  NTooltip,
  useDialog,
  useMessage,
} from 'naive-ui'
import {
  Columns2,
  Download,
  Eye,
  FileDown,
  FileText,
  PencilLine,
  TableOfContents,
} from 'lucide-vue-next'
import EditorSplit, { type ViewMode } from './EditorSplit.vue'
import SaveStatus from './SaveStatus.vue'
import OutlinePanel from './OutlinePanel.vue'
import { getMarkdown } from '@/markdown'
import { extractOutline, type OutlineItem } from '@/markdown/outline'
import SharePanel from './SharePanel.vue'
import { useNoteEditor } from '@/composables/useNoteEditor'
import { useWorkspaceStore } from '@/stores/workspace'
import { formatDateTime } from '@/utils/format'
import { exportNote, type ExportFormat } from '@/api/export'
import { uploadImage } from '@/api/images'
import { ApiError } from '@/api/http'
import { downloadBlob, safeFilename } from '@/utils/download'

const props = defineProps<{ noteId: number; dark: boolean; narrow: boolean }>()

const store = useWorkspaceStore()
const router = useRouter()
const dialog = useDialog()
const message = useMessage()

const editor = useNoteEditor(toRef(props, 'noteId'))
const { note, content, loading, loadError, status, lastError } = editor

// ---------- 视图模式 ----------
// 只提供「分栏」和「预览」两种，默认分栏
type SavedMode = 'split' | 'preview'
const MODE_KEY = 'underleaf-view-mode'
const savedMode = ref<SavedMode>(readMode())
function readMode(): SavedMode {
  try {
    // 以前保存的「编辑」模式等其他值一律按分栏处理
    if (localStorage.getItem(MODE_KEY) === 'preview') return 'preview'
  } catch {
    /* ignore */
  }
  return 'split'
}
/** 窄屏放不下两栏，分栏时只显示编辑区 */
const mode = computed<ViewMode>(() =>
  props.narrow && savedMode.value === 'split' ? 'edit' : savedMode.value,
)
function setMode(m: SavedMode) {
  savedMode.value = m
  try {
    localStorage.setItem(MODE_KEY, m)
  } catch {
    /* ignore */
  }
}
const modes = computed(() => [
  props.narrow
    ? { value: 'split' as const, label: '编辑', icon: PencilLine }
    : { value: 'split' as const, label: '分栏', icon: Columns2 },
  { value: 'preview' as const, label: '预览', icon: Eye },
])

// ---------- 目录 ----------
const OUTLINE_KEY = 'underleaf-outline'
const outlineOpen = ref(readOutlineOpen())
function readOutlineOpen() {
  try {
    return localStorage.getItem(OUTLINE_KEY) !== '0' // 默认打开
  } catch {
    return true
  }
}
/** 宽屏：作为右侧面板常驻；窄屏：从右侧滑出的抽屉，默认关闭 */
const drawerOpen = ref(false)
function toggleOutline() {
  if (props.narrow) {
    drawerOpen.value = !drawerOpen.value
    return
  }
  outlineOpen.value = !outlineOpen.value
  try {
    localStorage.setItem(OUTLINE_KEY, outlineOpen.value ? '1' : '0')
  } catch {
    /* ignore */
  }
}
const outlineActive = computed(() => (props.narrow ? drawerOpen.value : outlineOpen.value))

const outline = ref<OutlineItem[]>([])
const visibleLine = ref(0)
let outlineTimer: ReturnType<typeof setTimeout> | undefined
watch(
  content,
  (src) => {
    clearTimeout(outlineTimer)
    // 输入时稍作防抖，与预览渲染节奏一致
    outlineTimer = setTimeout(async () => {
      outline.value = extractOutline(await getMarkdown(), src)
    }, 300)
  },
  { immediate: true },
)
watch(
  () => props.noteId,
  () => (visibleLine.value = 0),
)
function onOutlineSelect(item: OutlineItem) {
  split.value?.scrollToLine(item.line)
  drawerOpen.value = false
}

// ---------- 标题 ----------
const meta = computed(() => store.noteById(props.noteId))
const title = ref('')
const titleMeasure = ref<HTMLSpanElement>()
const titleWidth = ref('auto')
/** 输入框宽度 = 标题文字宽度 + 输入框左右内边距 */
watch(
  title,
  async () => {
    await nextTick()
    const w = titleMeasure.value?.getBoundingClientRect().width
    if (w) titleWidth.value = `${Math.ceil(w) + 26}px`
  },
  { flush: 'post', immediate: true },
)
watch(
  () => meta.value?.title,
  (t) => (title.value = t ?? ''),
  { immediate: true },
)
async function commitTitle() {
  const t = title.value.trim()
  if (!meta.value || t === meta.value.title) return
  if (!t) {
    title.value = meta.value.title
    return
  }
  try {
    await store.updateNote(props.noteId, { title: t })
  } catch (e) {
    message.error((e as Error).message)
    title.value = meta.value.title
  }
}

// ---------- 保存时机 ----------
/** 编辑器失去焦点时立即保存（例如点去别处、切换窗口） */
function onEditorBlur() {
  if (status.value === 'dirty') void editor.save()
}

// ---------- 图片 ----------
/** 粘贴 / 拖入图片时上传，返回写入 Markdown 的站内地址 */
const uploadImageUrl = async (file: File) => (await uploadImage(file)).url

// ---------- 本地草稿 ----------
const { draftNotice } = editor
watch(draftNotice, (notice) => {
  if (!notice) return
  if (notice.kind === 'restored') {
    message.info(
      `已恢复上次未保存的内容（${formatDateTime(new Date(notice.savedAt).toISOString())}）`,
      {
        duration: 5000,
      },
    )
    draftNotice.value = null
    return
  }
  const { draft } = notice
  dialog.warning({
    title: '发现未保存的草稿',
    content: `本设备上有一份 ${formatDateTime(new Date(draft.savedAt).toISOString())} 未保存的草稿，但这篇笔记之后在其他地方被修改过。恢复草稿会覆盖那些修改。`,
    positiveText: '恢复草稿',
    negativeText: '丢弃草稿',
    closable: false,
    maskClosable: false,
    closeOnEsc: false,
    onPositiveClick: () => {
      editor.restoreDraft(draft)
      message.success('已恢复草稿')
    },
    onNegativeClick: () => editor.discardDraft(),
  })
})

// ---------- 版本冲突 ----------
watch(status, (s) => {
  if (s !== 'conflict') return
  dialog.warning({
    title: '这篇笔记已在其他设备上修改',
    content:
      '你在本设备上的修改与服务器上的最新版本冲突。可以用你的版本覆盖服务器，或放弃本设备的修改并加载服务器版本。',
    positiveText: '保留我的版本',
    negativeText: '使用服务器版本',
    closable: false,
    maskClosable: false,
    closeOnEsc: false,
    onPositiveClick: async () => {
      try {
        await editor.resolveKeepMine()
        message.success('已用你的版本覆盖')
      } catch (e) {
        message.error((e as Error).message)
      }
    },
    onNegativeClick: async () => {
      await editor.resolveUseRemote()
      message.info('已加载服务器上的最新版本')
    },
  })
})

// ---------- 导出 ----------
const exportOptions = [
  { label: '导出 PDF', key: 'pdf', icon: () => h(NIcon, null, () => h(FileDown)) },
  { label: '导出 Word', key: 'docx', icon: () => h(NIcon, null, () => h(FileText)) },
]
function onExport(key: string) {
  if (key === 'pdf' || key === 'docx') void exportFile(key)
}

/**
 * 导出 PDF / Word：把当前的标题和正文发给后端生成文件，然后直接下载。
 * 导出的是编辑器中的当前内容，不需要先保存。
 */
const exporting = ref(false)
async function exportFile(format: ExportFormat) {
  if (!note.value || exporting.value) return
  const exportTitle = title.value.trim() || note.value.title
  exporting.value = true
  const label = format === 'pdf' ? 'PDF' : 'Word'
  const loading = message.loading(`正在生成 ${label}…`, { duration: 0 })
  try {
    const blob = await exportNote(format, exportTitle, content.value)
    downloadBlob(blob, safeFilename(exportTitle, format))
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '导出失败，请稍后重试')
  } finally {
    loading.destroy()
    exporting.value = false
  }
}

const split = ref<InstanceType<typeof EditorSplit>>()
</script>

<template>
  <div class="note-workspace">
    <NResult v-if="loadError" status="404" :title="loadError" class="note-error">
      <template #footer>
        <NButton @click="router.push({ name: 'workspace' })">返回</NButton>
      </template>
    </NResult>
    <template v-else>
      <header class="note-toolbar">
        <NInput
          v-model:value="title"
          class="note-title"
          :style="{ width: titleWidth }"
          :bordered="false"
          :theme-overrides="{ color: 'transparent', colorFocus: 'transparent' }"
          placeholder="笔记标题"
          maxlength="100"
          @blur="commitTitle"
          @keydown.enter.prevent="($event.target as HTMLInputElement).blur()"
        />
        <!-- 隐藏的测量元素：按标题的实际文字宽度设置输入框宽度，保存状态紧跟在标题后面 -->
        <span ref="titleMeasure" class="title-measure" aria-hidden="true">{{
          title || '笔记标题'
        }}</span>
        <SaveStatus :status="status" :error="lastError" @save="editor.save()" />
        <div class="toolbar-spacer" />
        <NTooltip>
          <template #trigger>
            <button
              type="button"
              class="mode-btn outline-toggle"
              :class="{ active: outlineActive }"
              :aria-pressed="outlineActive"
              aria-label="目录"
              @click="toggleOutline"
            >
              <NIcon :size="16"><TableOfContents /></NIcon>
            </button>
          </template>
          {{ outlineActive ? '隐藏目录' : '显示目录' }}
        </NTooltip>
        <div class="mode-switch" role="radiogroup" aria-label="视图模式">
          <NTooltip v-for="m in modes" :key="m.value">
            <template #trigger>
              <button
                class="mode-btn"
                :class="{ active: savedMode === m.value }"
                role="radio"
                :aria-checked="savedMode === m.value"
                :aria-label="m.label"
                @click="setMode(m.value)"
              >
                <NIcon :size="16"><component :is="m.icon" /></NIcon>
              </button>
            </template>
            {{ m.label }}
          </NTooltip>
        </div>
        <SharePanel :note-id="noteId" :compact="narrow" />
        <NDropdown :options="exportOptions" trigger="click" @select="onExport">
          <NButton size="small" :loading="exporting" :aria-label="narrow ? '导出' : undefined">
            <template #icon
              ><NIcon><Download /></NIcon
            ></template>
            <span v-if="!narrow">导出</span>
          </NButton>
        </NDropdown>
      </header>
      <div class="note-body">
        <NSpin v-if="loading || !note" class="note-loading" />
        <EditorSplit
          v-else
          :key="note.id"
          ref="split"
          v-model="content"
          :mode="mode"
          :dark="dark"
          :readonly="status === 'conflict'"
          class="note-split"
          @save="editor.save()"
          :upload-image="uploadImageUrl"
          @blur="onEditorBlur"
          @image-error="(m: string) => message.error(m)"
          @visible-line="(line: number) => (visibleLine = line)"
        />
        <aside v-if="!narrow && outlineOpen && note && !loading" class="note-outline">
          <OutlinePanel :items="outline" :visible-line="visibleLine" @select="onOutlineSelect" />
        </aside>
      </div>
      <NDrawer v-if="narrow" v-model:show="drawerOpen" placement="right" :width="260">
        <NDrawerContent body-content-style="padding: 0">
          <OutlinePanel :items="outline" :visible-line="visibleLine" @select="onOutlineSelect" />
        </NDrawerContent>
      </NDrawer>
    </template>
  </div>
</template>

<style scoped>
.note-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
}
.note-error {
  margin-top: 12vh;
}
.note-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 48px;
  flex-shrink: 0;
  padding: 0 12px 0 8px;
  border-bottom: 1px solid var(--ul-border);
  background: var(--ul-bg);
}
.note-title {
  /* 宽度由 titleWidth 按标题文字计算，保存状态紧跟在标题后面 */
  flex: 0 1 auto;
  min-width: 80px;
  max-width: 420px;
  font-size: 15px;
  font-weight: 600;
}
.title-measure {
  position: absolute;
  visibility: hidden;
  white-space: pre;
  font-size: 15px;
  font-weight: 600;
  pointer-events: none;
}
.toolbar-spacer {
  flex: 1;
}
.mode-switch {
  display: inline-flex;
  padding: 2px;
  border-radius: 7px;
  background: var(--ul-bg-mute);
}
.mode-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 24px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--ul-text-2);
  cursor: pointer;
}
.mode-btn:hover {
  color: var(--ul-text);
}
.mode-btn.active {
  background: var(--ul-bg);
  color: var(--ul-accent);
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.12);
}
.note-body {
  flex: 1;
  min-height: 0;
  position: relative;
  display: flex;
}
.note-split {
  flex: 1;
  min-width: 0;
}
.note-outline {
  flex: 0 0 220px;
  min-width: 0;
  border-left: 1px solid var(--ul-border);
  background: var(--ul-bg);
}
.outline-toggle {
  height: 28px;
  border-radius: 6px;
}
.outline-toggle.active {
  background: var(--ul-accent-soft);
  box-shadow: none;
}
.note-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
@media (max-width: 767px) {
  .note-toolbar {
    gap: 6px;
    padding: 0 8px 0 4px;
  }
  .note-toolbar :deep(.save-status span) {
    display: none;
  }
}
</style>
