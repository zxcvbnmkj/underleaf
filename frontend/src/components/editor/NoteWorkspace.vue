<script setup lang="ts">
import { computed, h, ref, toRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton,
  NDropdown,
  NIcon,
  NInput,
  NResult,
  NSpin,
  NTooltip,
  useDialog,
  useMessage,
} from 'naive-ui'
import { Columns2, Download, Eye, FileDown, FileText, PencilLine } from 'lucide-vue-next'
import EditorSplit, { type ViewMode } from './EditorSplit.vue'
import SaveStatus from './SaveStatus.vue'
import SharePanel from './SharePanel.vue'
import { useNoteEditor } from '@/composables/useNoteEditor'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{ noteId: number; dark: boolean; narrow: boolean }>()

const store = useWorkspaceStore()
const router = useRouter()
const dialog = useDialog()
const message = useMessage()

const editor = useNoteEditor(toRef(props, 'noteId'))
const { note, content, loading, loadError, status, lastError } = editor

// ---------- 视图模式 ----------
const MODE_KEY = 'underleaf-view-mode'
const savedMode = ref<ViewMode>(readMode())
function readMode(): ViewMode {
  try {
    const m = localStorage.getItem(MODE_KEY)
    if (m === 'split' || m === 'edit' || m === 'preview') return m
  } catch {
    /* ignore */
  }
  return 'split'
}
/** 窄屏下不分栏 */
const mode = computed<ViewMode>(() =>
  props.narrow && savedMode.value === 'split' ? 'edit' : savedMode.value,
)
function setMode(m: ViewMode) {
  savedMode.value = m
  try {
    localStorage.setItem(MODE_KEY, m)
  } catch {
    /* ignore */
  }
}
const modes = computed(() =>
  [
    { value: 'edit' as const, label: '编辑', icon: PencilLine },
    { value: 'split' as const, label: '分栏', icon: Columns2 },
    { value: 'preview' as const, label: '预览', icon: Eye },
  ].filter((m) => !props.narrow || m.value !== 'split'),
)

// ---------- 标题 ----------
const meta = computed(() => store.noteById(props.noteId))
const title = ref('')
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
  if (key === 'pdf') void exportPdf()
  else message.info('导出 Word 需要后端服务（Pandoc），接入后端后可用')
}

/**
 * 导出 PDF：先保存，再打开打印页（与预览同一套渲染），由浏览器“另存为 PDF”。
 * 打印页读取的是服务器上的内容，所以必须先把本地修改存上去。
 */
async function exportPdf() {
  const n = note.value
  if (!n) return
  if (status.value === 'conflict') {
    message.warning('请先处理版本冲突，再导出')
    return
  }
  // 必须在点击事件里同步打开窗口，等保存完再打开会被浏览器当成弹窗拦截
  const win = window.open('', '_blank')
  if (!win) {
    message.error('浏览器拦截了新窗口，请允许本站弹出窗口后重试')
    return
  }
  win.document.title = '正在准备导出…'
  await editor.save()
  // save() 期间状态会变化，这里重新读取（避开 TS 对上面判断的类型收窄）
  const after: string = status.value
  if (after === 'conflict' || after === 'error') {
    win.close()
    message.error('保存失败，暂时无法导出，请稍后重试')
    return
  }
  win.location.href = router.resolve({
    name: 'print',
    params: { noteId: n.id },
    query: { auto: '1' },
  }).href
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
          :bordered="false"
          :theme-overrides="{ color: 'transparent', colorFocus: 'transparent' }"
          placeholder="笔记标题"
          maxlength="100"
          @blur="commitTitle"
          @keydown.enter.prevent="($event.target as HTMLInputElement).blur()"
        />
        <SaveStatus :status="status" :error="lastError" />
        <div class="toolbar-spacer" />
        <div class="mode-switch" role="radiogroup" aria-label="视图模式">
          <NTooltip v-for="m in modes" :key="m.value">
            <template #trigger>
              <button
                class="mode-btn"
                :class="{ active: mode === m.value }"
                role="radio"
                :aria-checked="mode === m.value"
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
          <NButton size="small" :aria-label="narrow ? '导出' : undefined">
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
          @save="editor.save()"
        />
      </div>
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
  flex: 0 1 360px;
  min-width: 80px;
  font-size: 15px;
  font-weight: 600;
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
