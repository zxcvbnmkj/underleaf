import { computed, onBeforeUnmount, ref, shallowRef, watch, type Ref } from 'vue'
import { notesApi } from '@/api/notes'
import { ApiError } from '@/api/http'
import { useWorkspaceStore } from '@/stores/workspace'
import type { Note } from '@/types'

export type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'conflict' | 'error'

const AUTOSAVE_DELAY = 1000

/**
 * 管理当前打开笔记的加载与自动保存。
 * 保存带版本号（乐观锁），服务端返回 409 时进入冲突状态，由界面让用户选择如何处理。
 */
export function useNoteEditor(noteId: Ref<number | null>) {
  const workspace = useWorkspaceStore()

  const note = shallowRef<Note | null>(null)
  const content = ref('')
  const loading = ref(false)
  const loadError = ref<string | null>(null)
  const status = ref<SaveStatus>('idle')
  const lastError = ref('')

  /** 最近一次成功保存到服务端的内容 */
  let savedContent = ''
  let version = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let saving: Promise<void> | null = null
  let loadSeq = 0

  const isDirty = computed(
    () => status.value === 'dirty' || status.value === 'saving' || status.value === 'error',
  )

  async function load(id: number) {
    const seq = ++loadSeq
    loading.value = true
    loadError.value = null
    try {
      const n = await notesApi.get(id)
      if (seq !== loadSeq) return
      note.value = n
      savedContent = n.content
      version = n.version
      content.value = n.content
      status.value = 'idle'
    } catch (e) {
      if (seq !== loadSeq) return
      note.value = null
      loadError.value =
        e instanceof ApiError && e.status === 404 ? '笔记不存在或已被删除' : '笔记加载失败'
    } finally {
      if (seq === loadSeq) loading.value = false
    }
  }

  async function doSave(): Promise<void> {
    const n = note.value
    if (!n || status.value === 'conflict') return
    const toSave = content.value
    if (toSave === savedContent) {
      status.value = status.value === 'idle' ? 'idle' : 'saved'
      return
    }
    status.value = 'saving'
    try {
      const meta = await notesApi.saveContent(n.id, toSave, version)
      if (note.value?.id !== n.id) return
      savedContent = toSave
      version = meta.version
      workspace.upsertNote(meta)
      // 保存期间又有新输入，继续排队保存
      if (content.value !== savedContent) schedule()
      else status.value = 'saved'
    } catch (e) {
      if (note.value?.id !== n.id) return
      if (e instanceof ApiError && e.status === 409) {
        status.value = 'conflict'
      } else {
        status.value = 'error'
        lastError.value = e instanceof Error ? e.message : '保存失败'
        // 网络等临时错误，稍后自动重试
        timer = setTimeout(save, 5000)
      }
    }
  }

  /** 立即保存（会等待正在进行的保存完成） */
  async function save() {
    clearTimeout(timer)
    while (saving) await saving
    saving = doSave().finally(() => (saving = null))
    await saving
  }

  function schedule() {
    clearTimeout(timer)
    status.value = 'dirty'
    timer = setTimeout(save, AUTOSAVE_DELAY)
  }

  watch(content, (val) => {
    if (!note.value || status.value === 'conflict') return
    if (val !== savedContent) schedule()
  })

  /** 冲突处理：放弃本地修改，加载服务端最新版本 */
  async function resolveUseRemote() {
    if (!note.value) return
    await load(note.value.id)
  }

  /** 冲突处理：用本地内容覆盖服务端（先取最新版本号再保存） */
  async function resolveKeepMine() {
    if (!note.value) return
    const latest = await notesApi.get(note.value.id)
    version = latest.version
    savedContent = latest.content
    status.value = 'dirty'
    await save()
  }

  watch(
    noteId,
    async (id, oldId) => {
      if (oldId != null && note.value && status.value !== 'conflict') await save()
      clearTimeout(timer)
      note.value = null
      status.value = 'idle'
      if (id != null) await load(id)
    },
    { immediate: true },
  )

  // 关闭页面时如有未保存内容，提醒用户
  const onBeforeUnload = (e: BeforeUnloadEvent) => {
    if (content.value !== savedContent && note.value) {
      void save()
      e.preventDefault()
    }
  }
  window.addEventListener('beforeunload', onBeforeUnload)
  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', onBeforeUnload)
    if (note.value && content.value !== savedContent && status.value !== 'conflict') void save()
    clearTimeout(timer)
  })

  return {
    note,
    content,
    loading,
    loadError,
    status,
    lastError,
    isDirty,
    save,
    resolveUseRemote,
    resolveKeepMine,
  }
}
