<script setup lang="ts">
import { computed, h, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton,
  NDropdown,
  NEmpty,
  NIcon,
  NInput,
  NTooltip,
  NTree,
  useDialog,
  useMessage,
  type DropdownOption,
  type TreeDropInfo,
  type TreeOption,
} from 'naive-ui'
import {
  Ellipsis,
  FilePlus,
  FileText,
  FolderClosed,
  FolderOpen,
  FolderPlus,
  Globe,
  Pencil,
  Search,
  Trash2,
} from 'lucide-vue-next'
import { folderKey, noteKey, useWorkspaceStore, type TreeNode } from '@/stores/workspace'
import { usePrompt } from '@/composables/usePrompt'

const props = defineProps<{ currentNoteId: number | null }>()
const emit = defineEmits<{ navigate: [] }>()

const store = useWorkspaceStore()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const prompt = usePrompt()

const pattern = ref('')

// ---------- 展开状态（本地记忆） ----------
const EXPANDED_KEY = 'underleaf-expanded'
const expandedKeys = ref<string[]>(readExpanded())
function readExpanded(): string[] {
  try {
    return JSON.parse(localStorage.getItem(EXPANDED_KEY) ?? '[]')
  } catch {
    return []
  }
}
watch(expandedKeys, (keys) => {
  try {
    localStorage.setItem(EXPANDED_KEY, JSON.stringify(keys))
  } catch {
    /* ignore */
  }
})
function expandFolder(folderId: number | null) {
  const keys = store.folderPath(folderId).map(folderKey)
  expandedKeys.value = Array.from(new Set([...expandedKeys.value, ...keys]))
}

// 打开笔记时自动展开它所在的文件夹
watch(
  () => [props.currentNoteId, store.loaded] as const,
  ([id]) => {
    if (id == null) return
    const note = store.noteById(id)
    if (note) expandFolder(note.folderId)
  },
  { immediate: true },
)

const selectedKeys = computed(() =>
  props.currentNoteId != null ? [noteKey(props.currentNoteId)] : [],
)

function openNote(id: number) {
  router.push({ name: 'workspace', params: { noteId: id } })
  emit('navigate')
}

// ---------- 渲染 ----------
const renderPrefix = ({ option }: { option: TreeOption }) => {
  const node = option as unknown as TreeNode
  const icon =
    node.type === 'note'
      ? FileText
      : expandedKeys.value.includes(node.key)
        ? FolderOpen
        : FolderClosed
  return h(NIcon, { size: 16, class: `tree-icon tree-icon-${node.type}` }, () => h(icon))
}

const renderSuffix = ({ option }: { option: TreeOption }) => {
  const node = option as unknown as TreeNode
  return h('span', { class: 'tree-suffix' }, [
    node.isPublic
      ? h(
          NTooltip,
          { placement: 'top' },
          {
            trigger: () => h(NIcon, { size: 14, class: 'public-icon' }, () => h(Globe)),
            default: () => '已公开分享',
          },
        )
      : null,
    h(
      'button',
      {
        class: 'tree-more',
        title: '更多操作',
        onClick: (e: MouseEvent) => {
          e.stopPropagation()
          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
          showMenu(node, rect.left, rect.bottom)
        },
      },
      [h(NIcon, { size: 16 }, () => h(Ellipsis))],
    ),
  ])
}

const nodeProps = ({ option }: { option: TreeOption }) => {
  const node = option as unknown as TreeNode
  return {
    onClick() {
      if (node.type === 'note') openNote(node.id)
      else {
        const keys = expandedKeys.value
        expandedKeys.value = keys.includes(node.key)
          ? keys.filter((k) => k !== node.key)
          : [...keys, node.key]
      }
    },
    onContextmenu(e: MouseEvent) {
      e.preventDefault()
      e.stopPropagation()
      showMenu(node, e.clientX, e.clientY)
    },
  }
}

// ---------- 右键菜单 ----------
const menu = ref({ show: false, x: 0, y: 0, target: null as TreeNode | null })
const icon = (c: unknown) => () => h(NIcon, null, () => h(c as never))

const menuOptions = computed<DropdownOption[]>(() => {
  const t = menu.value.target
  if (!t) {
    return [
      { label: '新建笔记', key: 'new-note', icon: icon(FilePlus) },
      { label: '新建文件夹', key: 'new-folder', icon: icon(FolderPlus) },
    ]
  }
  if (t.type === 'folder') {
    return [
      { label: '新建笔记', key: 'new-note', icon: icon(FilePlus) },
      { label: '新建子文件夹', key: 'new-folder', icon: icon(FolderPlus) },
      { type: 'divider', key: 'd1' },
      { label: '重命名', key: 'rename', icon: icon(Pencil) },
      { label: '删除', key: 'delete', icon: icon(Trash2), props: { class: 'danger-option' } },
    ]
  }
  return [
    { label: '重命名', key: 'rename', icon: icon(Pencil) },
    { label: '删除', key: 'delete', icon: icon(Trash2), props: { class: 'danger-option' } },
  ]
})

function showMenu(target: TreeNode | null, x: number, y: number) {
  menu.value.show = false
  nextTick(() => (menu.value = { show: true, x, y, target }))
}

function onBlankContextmenu(e: MouseEvent) {
  e.preventDefault()
  showMenu(null, e.clientX, e.clientY)
}

async function onMenuSelect(key: string) {
  menu.value.show = false
  const t = menu.value.target
  const folderId = t?.type === 'folder' ? t.id : null
  await run(async () => {
    if (key === 'new-note') await newNote(folderId)
    else if (key === 'new-folder') await newFolder(folderId)
    else if (key === 'rename' && t) await rename(t)
    else if (key === 'delete' && t) remove(t)
  })
}

async function run(fn: () => Promise<unknown>) {
  try {
    await fn()
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function newNote(folderId: number | null) {
  const note = await store.createNote(folderId)
  expandFolder(folderId)
  openNote(note.id)
}

async function newFolder(parentId: number | null) {
  const name = await prompt({ title: '新建文件夹', placeholder: '文件夹名称' })
  if (!name) return
  const folder = await store.createFolder(name, parentId)
  expandFolder(folder.id)
}

async function rename(t: TreeNode) {
  const name = await prompt({
    title: t.type === 'folder' ? '重命名文件夹' : '重命名笔记',
    value: t.label,
  })
  if (!name || name === t.label) return
  if (t.type === 'folder') await store.updateFolder(t.id, { name })
  else await store.updateNote(t.id, { title: name })
}

function remove(t: TreeNode) {
  let content = `确定删除笔记「${t.label}」吗？删除后无法恢复。`
  if (t.type === 'folder') {
    const s = store.folderStats(t.id)
    const parts = [s.folders && `${s.folders} 个子文件夹`, s.notes && `${s.notes} 篇笔记`].filter(
      Boolean,
    )
    content = parts.length
      ? `文件夹「${t.label}」中包含 ${parts.join('、')}，将一并删除且无法恢复。确定删除吗？`
      : `确定删除文件夹「${t.label}」吗？`
  }
  dialog.warning({
    title: '删除确认',
    content,
    positiveText: '删除',
    negativeText: '取消',
    positiveButtonProps: { type: 'error' },
    onPositiveClick: async () => {
      try {
        if (t.type === 'note') {
          await store.deleteNote(t.id)
          if (props.currentNoteId === t.id) router.push({ name: 'workspace' })
        } else {
          const removed = await store.deleteFolder(t.id)
          if (props.currentNoteId != null && removed.includes(props.currentNoteId)) {
            router.push({ name: 'workspace' })
          }
        }
        message.success('已删除')
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

// ---------- 拖拽移动 ----------
async function onDrop({ node, dragNode, dropPosition }: TreeDropInfo) {
  const target = node as unknown as TreeNode
  const dragged = dragNode as unknown as TreeNode
  let parentId: number | null
  if (dropPosition === 'inside' && target.type === 'folder') parentId = target.id
  else if (target.type === 'folder') parentId = store.folderById(target.id)?.parentId ?? null
  else parentId = store.noteById(target.id)?.folderId ?? null

  try {
    if (dragged.type === 'note') {
      if (store.noteById(dragged.id)?.folderId === parentId) return
      await store.updateNote(dragged.id, { folderId: parentId })
    } else {
      if (store.folderById(dragged.id)?.parentId === parentId) return
      if (parentId !== null && store.isDescendant(parentId, dragged.id)) {
        message.warning('不能把文件夹移动到它自己的子文件夹中')
        return
      }
      await store.updateFolder(dragged.id, { parentId })
    }
    expandFolder(parentId)
  } catch (e) {
    message.error((e as Error).message)
  }
}

defineExpose({ newNote, newFolder })
</script>

<template>
  <div class="folder-tree">
    <div class="tree-header">
      <span class="tree-title">我的笔记</span>
      <div class="tree-actions">
        <NTooltip>
          <template #trigger>
            <NButton
              quaternary
              circle
              size="small"
              aria-label="新建笔记"
              @click="run(() => newNote(null))"
            >
              <template #icon
                ><NIcon><FilePlus /></NIcon
              ></template>
            </NButton>
          </template>
          新建笔记
        </NTooltip>
        <NTooltip>
          <template #trigger>
            <NButton
              quaternary
              circle
              size="small"
              aria-label="新建文件夹"
              @click="run(() => newFolder(null))"
            >
              <template #icon
                ><NIcon><FolderPlus /></NIcon
              ></template>
            </NButton>
          </template>
          新建文件夹
        </NTooltip>
      </div>
    </div>
    <div class="tree-search">
      <NInput v-model:value="pattern" size="small" placeholder="搜索标题" clearable>
        <template #prefix
          ><NIcon><Search /></NIcon
        ></template>
      </NInput>
    </div>
    <div class="tree-body" @contextmenu="onBlankContextmenu">
      <NTree
        v-if="store.tree.length"
        block-line
        draggable
        :data="store.tree as unknown as TreeOption[]"
        :pattern="pattern"
        :show-irrelevant-nodes="false"
        :selected-keys="selectedKeys"
        :expanded-keys="expandedKeys"
        :render-prefix="renderPrefix"
        :render-suffix="renderSuffix"
        :node-props="nodeProps"
        :cancelable="false"
        :expand-on-click="false"
        @update:expanded-keys="(keys: string[]) => (expandedKeys = keys)"
        @drop="onDrop"
      />
      <NEmpty v-else-if="store.loaded" description="还没有笔记" class="tree-empty">
        <template #extra>
          <NButton size="small" @click="run(() => newNote(null))">新建一篇笔记</NButton>
        </template>
      </NEmpty>
    </div>
    <NDropdown
      trigger="manual"
      placement="bottom-start"
      :show="menu.show"
      :x="menu.x"
      :y="menu.y"
      :options="menuOptions"
      @select="onMenuSelect"
      @clickoutside="menu.show = false"
    />
  </div>
</template>

<style scoped>
.folder-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 10px 6px 16px;
}
.tree-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--ul-text-2);
}
.tree-actions {
  display: flex;
  gap: 2px;
}
.tree-search {
  padding: 4px 12px 8px;
}
.tree-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 6px 24px;
}
.tree-empty {
  margin-top: 48px;
}
.tree-body :deep(.n-tree-node) {
  border-radius: 6px;
}
.tree-body :deep(.n-tree-node-content) {
  padding-right: 4px;
}
.tree-body :deep(.n-tree-node-content__text) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tree-body :deep(.tree-icon-folder) {
  color: var(--ul-folder);
}
.tree-body :deep(.tree-icon-note) {
  color: var(--ul-text-3);
}
.tree-body :deep(.n-tree-node--selected .tree-icon-note) {
  color: var(--ul-accent);
}
.tree-body :deep(.tree-suffix) {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.tree-body :deep(.public-icon) {
  color: var(--ul-accent);
}
.tree-body :deep(.tree-more) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--ul-text-2);
  cursor: pointer;
  opacity: 0;
}
.tree-body :deep(.n-tree-node:hover .tree-more),
.tree-body :deep(.tree-more:focus-visible) {
  opacity: 1;
}
.tree-body :deep(.tree-more:hover) {
  background: var(--ul-bg-mute);
}
@media (hover: none) {
  .tree-body :deep(.tree-more) {
    opacity: 1;
  }
}
</style>
