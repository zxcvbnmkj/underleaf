/**
 * 本地草稿：输入时把正文写入 localStorage，防止停电、浏览器崩溃等情况下丢失未保存的内容。
 *
 * - 只存在当前浏览器，不经过服务器；保存到服务器成功后删除
 * - 按用户和笔记区分：underleaf-draft:{userId}:{noteId}
 * - localStorage 不可用或超出容量（约 5MB）时静默失败，不影响正常编辑
 */

export interface NoteDraft {
  content: string
  /** 草稿所基于的服务端版本号，用来判断服务端之后是否被修改过 */
  baseVersion: number
  /** 草稿最后写入的时间（毫秒时间戳） */
  savedAt: number
}

const PREFIX = 'underleaf-draft:'

const keyOf = (userId: number, noteId: number) => `${PREFIX}${userId}:${noteId}`

export function readDraft(userId: number, noteId: number): NoteDraft | null {
  try {
    const raw = localStorage.getItem(keyOf(userId, noteId))
    if (!raw) return null
    const draft = JSON.parse(raw) as NoteDraft
    return typeof draft.content === 'string' && typeof draft.baseVersion === 'number' ? draft : null
  } catch {
    return null
  }
}

export function writeDraft(userId: number, noteId: number, draft: NoteDraft) {
  try {
    localStorage.setItem(keyOf(userId, noteId), JSON.stringify(draft))
  } catch {
    /* 容量不足或存储不可用 */
  }
}

export function removeDraft(userId: number, noteId: number) {
  try {
    localStorage.removeItem(keyOf(userId, noteId))
  } catch {
    /* ignore */
  }
}
