import type { Folder } from '@/types'
import { http } from './http'

export const foldersApi = {
  list: () => http.get<Folder[]>('/folders'),
  create: (name: string, parentId: number | null) =>
    http.post<Folder>('/folders', { name, parentId }),
  update: (id: number, data: { name?: string; parentId?: number | null }) =>
    http.patch<Folder>(`/folders/${id}`, data),
  /** 级联删除子文件夹和其中的笔记 */
  remove: (id: number) => http.delete<void>(`/folders/${id}`),
}
