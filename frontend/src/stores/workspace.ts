import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { foldersApi } from '@/api/folders'
import { notesApi } from '@/api/notes'
import type { Folder, NoteMeta } from '@/types'

export interface TreeNode {
  key: string
  type: 'folder' | 'note'
  id: number
  label: string
  children?: TreeNode[]
  isLeaf: boolean
  isPublic?: boolean
}

export const folderKey = (id: number) => `f:${id}`
export const noteKey = (id: number) => `n:${id}`

const byName = (a: { label: string }, b: { label: string }) =>
  a.label.localeCompare(b.label, 'zh-Hans-CN', { numeric: true })

export const useWorkspaceStore = defineStore('workspace', () => {
  const folders = ref<Folder[]>([])
  const notes = ref<NoteMeta[]>([])
  const loaded = ref(false)

  async function load() {
    const [f, n] = await Promise.all([foldersApi.list(), notesApi.list()])
    folders.value = f
    notes.value = n
    loaded.value = true
  }

  function reset() {
    folders.value = []
    notes.value = []
    loaded.value = false
  }

  /** 由扁平的文件夹和笔记组装成树：文件夹在前，按名称排序 */
  const tree = computed<TreeNode[]>(() => {
    const children = new Map<number | null, TreeNode[]>()
    const push = (parent: number | null, node: TreeNode) => {
      if (!children.has(parent)) children.set(parent, [])
      children.get(parent)!.push(node)
    }
    const folderNodes = new Map<number, TreeNode>()
    for (const f of folders.value) {
      const node: TreeNode = {
        key: folderKey(f.id),
        type: 'folder',
        id: f.id,
        label: f.name,
        isLeaf: false,
      }
      folderNodes.set(f.id, node)
    }
    for (const f of folders.value) {
      // 父文件夹不存在时挂到根目录，避免数据异常导致节点丢失
      const parent = f.parentId !== null && folderNodes.has(f.parentId) ? f.parentId : null
      push(parent, folderNodes.get(f.id)!)
    }
    for (const n of notes.value) {
      const parent = n.folderId !== null && folderNodes.has(n.folderId) ? n.folderId : null
      push(parent, {
        key: noteKey(n.id),
        type: 'note',
        id: n.id,
        label: n.title,
        isLeaf: true,
        isPublic: n.isPublic,
      })
    }
    const build = (parent: number | null): TreeNode[] => {
      const list = children.get(parent) ?? []
      const fs = list.filter((x) => x.type === 'folder').sort(byName)
      const ns = list.filter((x) => x.type === 'note').sort(byName)
      for (const f of fs) f.children = build(f.id)
      return [...fs, ...ns]
    }
    return build(null)
  })

  const noteById = (id: number) => notes.value.find((n) => n.id === id)
  const folderById = (id: number) => folders.value.find((f) => f.id === id)

  /** 文件夹的祖先链（含自身），用于展开树 */
  function folderPath(id: number | null): number[] {
    const path: number[] = []
    const seen = new Set<number>()
    for (let cur = id; cur !== null && !seen.has(cur); cur = folderById(cur)?.parentId ?? null) {
      seen.add(cur)
      path.unshift(cur)
    }
    return path
  }

  function isDescendant(folderId: number, ancestorId: number) {
    return folderPath(folderId).includes(ancestorId)
  }

  function upsertNote(meta: NoteMeta) {
    const i = notes.value.findIndex((n) => n.id === meta.id)
    if (i >= 0) notes.value[i] = { ...notes.value[i], ...meta }
    else notes.value.push(meta)
  }

  // ---------- 文件夹 ----------
  async function createFolder(name: string, parentId: number | null) {
    const folder = await foldersApi.create(name, parentId)
    folders.value.push(folder)
    return folder
  }
  async function updateFolder(id: number, data: { name?: string; parentId?: number | null }) {
    const folder = await foldersApi.update(id, data)
    const i = folders.value.findIndex((f) => f.id === id)
    if (i >= 0) folders.value[i] = folder
  }
  /** 删除文件夹及其所有子孙内容，返回被删除的笔记 id */
  async function deleteFolder(id: number): Promise<number[]> {
    await foldersApi.remove(id)
    const removed = new Set(folders.value.filter((f) => isDescendant(f.id, id)).map((f) => f.id))
    const removedNotes = notes.value
      .filter((n) => n.folderId !== null && removed.has(n.folderId))
      .map((n) => n.id)
    folders.value = folders.value.filter((f) => !removed.has(f.id))
    notes.value = notes.value.filter((n) => !removedNotes.includes(n.id))
    return removedNotes
  }
  /** 统计文件夹下（含子孙）的文件夹数和笔记数 */
  function folderStats(id: number) {
    const ids = new Set(folders.value.filter((f) => isDescendant(f.id, id)).map((f) => f.id))
    return {
      folders: ids.size - 1,
      notes: notes.value.filter((n) => n.folderId !== null && ids.has(n.folderId)).length,
    }
  }

  // ---------- 笔记 ----------
  async function createNote(folderId: number | null, title = '未命名笔记') {
    const note = await notesApi.create(title, folderId)
    upsertNote(note)
    return note
  }
  async function updateNote(
    id: number,
    data: { title?: string; folderId?: number | null; isPublic?: boolean },
  ) {
    upsertNote(await notesApi.update(id, data))
  }
  async function deleteNote(id: number) {
    await notesApi.remove(id)
    notes.value = notes.value.filter((n) => n.id !== id)
  }

  return {
    folders,
    notes,
    loaded,
    tree,
    load,
    reset,
    noteById,
    folderById,
    folderPath,
    isDescendant,
    upsertNote,
    createFolder,
    updateFolder,
    deleteFolder,
    folderStats,
    createNote,
    updateNote,
    deleteNote,
  }
})
