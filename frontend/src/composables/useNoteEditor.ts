import { computed, onBeforeUnmount, ref, shallowRef, watch, type Ref } from 'vue'
import { notesApi } from '@/api/notes'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import { readDraft, removeDraft, writeDraft, type NoteDraft } from './noteDrafts'
import type { Note } from '@/types'

export type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'conflict' | 'error'

/** 停止输入多久后自动保存 */
const IDLE_DELAY = 30_000
/** 持续输入时，最长多久必须保存一次（避免长时间写作一直不同步到服务器） */
const MAX_WAIT = 120_000
/** 网络等临时错误后的重试间隔 */
const RETRY_DELAY = 5_000
/** 本地草稿的写入防抖（只写 localStorage，不访问服务器） */
const DRAFT_DELAY = 500

/** 打开笔记时发现的本地草稿 */
export type DraftNotice =
  /** 服务端在草稿之后没有被修改过，已自动恢复 */
  | { kind: 'restored'; savedAt: number }
  /** 服务端在草稿之后被修改过（例如在其他设备上），需要用户选择 */
  | { kind: 'conflict'; draft: NoteDraft }

/**
 * 管理当前打开笔记的加载与保存。
 *
 * 保存时机（readme「保存策略」）：停止输入 30 秒、持续输入满 2 分钟、编辑器失去焦点
 * （由界面调用 save）、页面切到后台、切换笔记、Ctrl/⌘+S。
 * 输入时同时写本地草稿，停电或浏览器崩溃后重新打开可以恢复。
 * 保存带版本号（乐观锁），服务端返回 409 时进入冲突状态，由界面让用户选择如何处理。
 */
export function useNoteEditor(noteId: Ref<number | null>) {
  const workspace = useWorkspaceStore()
  const auth = useAuthStore()

  const note = shallowRef<Note | null>(null)
  const content = ref('')
  const loading = ref(false)
  const loadError = ref<string | null>(null)
  const status = ref<SaveStatus>('idle')
  const lastError = ref('')
  const draftNotice = ref<DraftNotice | null>(null)

  /** 最近一次成功保存到服务端的内容 */
  let savedContent = ''
  let version = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let draftTimer: ReturnType<typeof setTimeout> | undefined
  /** 本轮未保存修改的开始时间，用于 MAX_WAIT */
  let dirtySince = 0
  let saving: Promise<void> | null = null
  let loadSeq = 0

  const isDirty = computed(
    () => status.value === 'dirty' || status.value === 'saving' || status.value === 'error',
  )

  // ---------- 本地草稿 ----------
  function flushDraft() {
    clearTimeout(draftTimer)
    const n = note.value
    const userId = auth.user?.id
    if (!n || userId == null) return
    if (content.value === savedContent) removeDraft(userId, n.id)
    else
      writeDraft(userId, n.id, {
        content: content.value,
        baseVersion: version,
        savedAt: Date.now(),
      })
  }

  function scheduleDraft() {
    clearTimeout(draftTimer)
    draftTimer = setTimeout(flushDraft, DRAFT_DELAY)
  }

  function dropDraft(id: number) {
    if (auth.user) removeDraft(auth.user.id, id)
  }

  /** 加载笔记后检查本地草稿 */
  function checkDraft(n: Note) {
    const draft = auth.user ? readDraft(auth.user.id, n.id) : null
    if (!draft) return
    if (draft.content === n.content) {
      dropDraft(n.id)
    } else if (draft.baseVersion === n.version) {
      // 服务端没有变化，草稿就是上次没来得及保存的内容，直接恢复
      content.value = draft.content
      draftNotice.value = { kind: 'restored', savedAt: draft.savedAt }
    } else {
      draftNotice.value = { kind: 'conflict', draft }
    }
  }

  /** 用户选择恢复草稿（服务端已被修改的情况）：以服务端最新版本为基础，用草稿覆盖 */
  function restoreDraft(draft: NoteDraft) {
    content.value = draft.content
    draftNotice.value = null
  }

  function discardDraft() {
    if (note.value) dropDraft(note.value.id)
    draftNotice.value = null
  }

  // ---------- 加载 ----------
  async function load(id: number) {
    const seq = ++loadSeq
    loading.value = true
    loadError.value = null
    draftNotice.value = null
    try {
      const n = await notesApi.get(id)
      if (seq !== loadSeq) return
      note.value = n
      savedContent = n.content
      version = n.version
      content.value = n.content
      status.value = 'idle'
      checkDraft(n)
    } catch (e) {
      if (seq !== loadSeq) return
      note.value = null
      loadError.value =
        e instanceof ApiError && e.status === 404 ? '笔记不存在或已被删除' : '笔记加载失败'
    } finally {
      if (seq === loadSeq) loading.value = false
    }
  }

  // ---------- 保存 ----------
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
      if (content.value !== savedContent) {
        // 保存期间又有新输入，继续排队保存
        schedule()
      } else {
        status.value = 'saved'
        dirtySince = 0
      }
      flushDraft()
    } catch (e) {
      if (note.value?.id !== n.id) return
      if (e instanceof ApiError && e.status === 409) {
        status.value = 'conflict'
      } else {
        status.value = 'error'
        lastError.value = e instanceof Error ? e.message : '保存失败'
        // 网络等临时错误，稍后自动重试（期间内容仍保存在本地草稿中）
        timer = setTimeout(save, RETRY_DELAY)
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

  /** 安排自动保存：停止输入 IDLE_DELAY 后保存，但距本轮第一次修改最长不超过 MAX_WAIT */
  function schedule() {
    clearTimeout(timer)
    status.value = 'dirty'
    const now = Date.now()
    if (!dirtySince) dirtySince = now
    const delay = Math.min(IDLE_DELAY, Math.max(0, dirtySince + MAX_WAIT - now))
    timer = setTimeout(save, delay)
  }

  watch(content, (val) => {
    if (!note.value || status.value === 'conflict') return
    scheduleDraft()
    if (val !== savedContent) schedule()
  })

  // ---------- 冲突处理 ----------
  /** 放弃本地修改，加载服务端最新版本 */
  async function resolveUseRemote() {
    if (!note.value) return
    dropDraft(note.value.id)
    await load(note.value.id)
  }

  /** 用本地内容覆盖服务端（先取最新版本号再保存） */
  async function resolveKeepMine() {
    if (!note.value) return
    const latest = await notesApi.get(note.value.id)
    version = latest.version
    savedContent = latest.content
    status.value = 'dirty'
    await save()
  }

  // ---------- 切换笔记 / 离开页面 ----------
  watch(
    noteId,
    async (id, oldId) => {
      if (oldId != null && note.value && status.value !== 'conflict') {
        flushDraft()
        await save()
      }
      clearTimeout(timer)
      clearTimeout(draftTimer)
      note.value = null
      status.value = 'idle'
      dirtySince = 0
      if (id != null) await load(id)
    },
    { immediate: true },
  )

  const hasUnsaved = () => !!note.value && content.value !== savedContent

  // 关闭 / 刷新页面时如有未保存内容，提醒用户（停电、崩溃等情况由本地草稿兜底）
  const onBeforeUnload = (e: BeforeUnloadEvent) => {
    if (!hasUnsaved()) return
    flushDraft()
    void save()
    e.preventDefault()
  }
  // 切到其他标签页、最小化窗口、手机切到后台时立即保存
  const onVisibilityChange = () => {
    if (document.visibilityState !== 'hidden' || !hasUnsaved()) return
    flushDraft()
    if (status.value !== 'conflict') void save()
  }
  window.addEventListener('beforeunload', onBeforeUnload)
  document.addEventListener('visibilitychange', onVisibilityChange)
  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', onBeforeUnload)
    document.removeEventListener('visibilitychange', onVisibilityChange)
    if (hasUnsaved() && status.value !== 'conflict') {
      flushDraft()
      void save()
    }
    clearTimeout(timer)
    clearTimeout(draftTimer)
  })

  return {
    note,
    content,
    loading,
    loadError,
    status,
    lastError,
    isDirty,
    draftNotice,
    save,
    resolveUseRemote,
    resolveKeepMine,
    restoreDraft,
    discardDraft,
  }
}
