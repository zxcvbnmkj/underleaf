import type { Note, NoteMeta, SharedNote } from '@/types'
import { http } from './http'

export const notesApi = {
  list: () => http.get<NoteMeta[]>('/notes'),
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
