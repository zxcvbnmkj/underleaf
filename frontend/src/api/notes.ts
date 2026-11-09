import type { Note, NoteMeta, RecentNote, SharedNote } from '@/types'
import { http } from './http'

export const notesApi = {
  list: () => http.get<NoteMeta[]>('/notes'),
  /** 最近编辑的笔记，带正文摘要 */
  recent: (limit = 8) => http.get<RecentNote[]>(`/notes/recent?limit=${limit}`),
  /** 全文搜索（标题 + 正文），空格分隔多个关键词；摘要为命中处附近的文字 */
  search: (q: string, limit = 30) =>
    http.get<RecentNote[]>(`/notes/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  get: (id: number) => http.get<Note>(`/notes/${id}`),
  create: (title: string, folderId: number | null) =>
    http.post<Note>('/notes', { title, folderId }),
  /** 修改元信息（标题、所在文件夹、是否公开），不涉及版本号 */
  update: (id: number, data: { title?: string; folderId?: number | null; isPublic?: boolean }) =>
    http.patch<NoteMeta>(`/notes/${id}`, data),
  /** 保存正文，带乐观锁：version 与服务端不一致时返回 409 */
  saveContent: (id: number, content: string, version: number) =>
    http.put<NoteMeta>(`/notes/${id}/content`, { content, version }),
  remove: (id: number) => http.delete<void>(`/notes/${id}`),
  getShared: (publicId: string) => http.get<SharedNote>(`/share/${publicId}`),
}
