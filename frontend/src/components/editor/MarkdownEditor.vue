<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorView, keymap, placeholder as cmPlaceholder } from '@codemirror/view'
import { Compartment, EditorState } from '@codemirror/state'
import { basicSetup } from 'codemirror'
import { indentWithTab } from '@codemirror/commands'
import { markdown, markdownLanguage } from '@codemirror/lang-markdown'
import { languages } from '@codemirror/language-data'
import { oneDark } from '@codemirror/theme-one-dark'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { Tag, styleTags, tags } from '@lezer/highlight'

// 只给行内代码单独打标，避免未识别语言的代码块整段被套上行内底色
const inlineCode = Tag.define(tags.monospace)

const props = defineProps<{
  modelValue: string
  dark: boolean
  readonly?: boolean
  /** 上传图片并返回地址；提供后支持粘贴、拖入图片 */
  uploadImage?: (file: File) => Promise<string>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  /** 滚动时报告顶部可见位置：行号（从 0 开始）+ 该行内的偏移比例 */
  scroll: [line: number]
  save: []
  /** 编辑器失去焦点（用于触发保存） */
  blur: []
  /** 图片上传失败 */
  imageError: [message: string]
}>()

const host = ref<HTMLDivElement>()
let view: EditorView | null = null
const themeConf = new Compartment()
const readonlyConf = new Compartment()

const lightTheme = EditorView.theme({
  '&': { backgroundColor: 'var(--ul-bg)', color: 'var(--ul-text)' },
  '.cm-gutters': {
    backgroundColor: 'var(--ul-bg)',
    borderRight: '1px solid var(--ul-border)',
    color: 'var(--ul-text-3)',
  },
  '.cm-activeLineGutter': { backgroundColor: 'var(--ul-bg-soft)' },
  // 必须半透明：选中高亮画在文字下层，不透明的当前行背景会把同一行内的选中区域完全盖住
  '.cm-activeLine': { backgroundColor: 'rgb(0 0 0 / 0.025)' },
  // 选中颜色：聚焦时用品牌绿的浅色调，失焦时为浅灰
  '&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground': {
    backgroundColor: 'rgb(47 133 90 / 0.22)',
  },
  '.cm-selectionLayer .cm-selectionBackground': { backgroundColor: 'rgb(0 0 0 / 0.1)' },
})

const baseTheme = EditorView.theme({
  '&': { height: '100%', fontSize: '14px' },
  '.cm-scroller': {
    fontFamily: 'var(--ul-font-mono)',
    lineHeight: '1.7',
  },
  '.cm-content': { padding: '16px 0 40vh' },
  '.cm-line': { padding: '0 20px 0 12px' },
  '&.cm-focused': { outline: 'none' },
})

/** Markdown 源码的排版：标题加粗放大但不加下划线，标记符号弱化 */
const markdownStyle = syntaxHighlighting(
  HighlightStyle.define([
    { tag: tags.heading1, fontWeight: '700', fontSize: '1.3em' },
    { tag: tags.heading2, fontWeight: '700', fontSize: '1.18em' },
    { tag: tags.heading3, fontWeight: '700', fontSize: '1.08em' },
    { tag: [tags.heading4, tags.heading5, tags.heading6], fontWeight: '700' },
    { tag: tags.strong, fontWeight: '700', color: 'var(--ul-md-strong)' },
    { tag: tags.emphasis, fontStyle: 'italic', color: 'var(--ul-md-em)' },
    { tag: tags.strikethrough, textDecoration: 'line-through', color: 'var(--ul-text-2)' },
    { tag: [tags.link, tags.url], color: 'var(--ul-accent)' },
    // 反引号、星号等标记符号弱化，衬托中间的内容
    { tag: tags.processingInstruction, color: 'var(--ul-text-3)' },
    { tag: tags.quote, color: 'var(--ul-text-2)' },
    // 行内代码：醒目的颜色 + 淡底色，与预览区一致
    {
      tag: inlineCode,
      color: 'var(--ul-code-text)',
      backgroundColor: 'var(--ul-code-inline-bg)',
      borderRadius: '3px',
    },
  ]),
)

/** 覆盖 oneDark 的选中色：原色 #3E4451 与背景 #282C34 太接近，几乎看不出选中了什么 */
const darkOverrides = EditorView.theme(
  {
    '&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground': {
      backgroundColor: 'rgb(79 178 127 / 0.3)',
    },
    '.cm-selectionLayer .cm-selectionBackground': { backgroundColor: 'rgb(255 255 255 / 0.12)' },
  },
  { dark: true },
)

function themeExt(dark: boolean) {
  // CodeMirror 中排在前面的扩展优先级更高，覆盖样式要放在 oneDark 之前
  return dark ? [darkOverrides, oneDark] : lightTheme
}

// ---------- 粘贴 / 拖入图片 ----------
let uploadSeq = 0
const canUpload = () => !!props.uploadImage && !props.readonly

function imageFiles(data: DataTransfer | null): File[] {
  return Array.from(data?.files ?? []).filter((f) => f.type.startsWith('image/'))
}

/** 图片说明文字：文件名去掉扩展名（截图粘贴时通常为 image） */
const altOf = (file: File) => file.name.replace(/\.[^.]+$/, '').replace(/[[\]]/g, '') || 'image'

/**
 * 先在 [from, to] 处插入占位文字，上传完成后替换为图片链接；失败则删除占位并提示。
 * 上传期间可以继续编辑，按占位文字（带唯一编号）重新定位，不依赖插入时的位置。
 */
function insertImages(files: File[], from: number, to: number) {
  if (!view || !props.uploadImage) return
  const placeholders = files.map(() => `![上传中…（${++uploadSeq}）]()`)
  // 图片单独成段：前后有文字时自动补空行，多张图片之间也用空行分隔
  const doc = view.state.doc
  const startLine = doc.lineAt(from)
  const endLine = doc.lineAt(to)
  const prevLine = startLine.number > 1 ? doc.line(startLine.number - 1) : null
  const prefix = from > startLine.from ? '\n\n' : prevLine && prevLine.length ? '\n' : ''
  const suffix = to < endLine.to ? '\n\n' : ''
  const body = placeholders.join('\n\n')
  view.dispatch({
    changes: { from, to, insert: prefix + body + suffix },
    selection: { anchor: from + prefix.length + body.length },
  })
  files.forEach((file, i) => {
    const placeholder = placeholders[i]!
    props.uploadImage!(file).then(
      (url) => replacePlaceholder(placeholder, `![${altOf(file)}](${url})`),
      (e: unknown) => {
        replacePlaceholder(placeholder, '')
        emit('imageError', e instanceof Error ? e.message : '图片上传失败')
      },
    )
  })
}

function replacePlaceholder(placeholder: string, insert: string) {
  if (!view) return
  const index = view.state.doc.toString().indexOf(placeholder)
  if (index < 0) return // 占位文字已被用户删除
  view.dispatch({ changes: { from: index, to: index + placeholder.length, insert } })
}

function emitScroll() {
  if (!view) return
  const top = view.scrollDOM.scrollTop
  const block = view.lineBlockAtHeight(top)
  const line = view.state.doc.lineAt(block.from).number - 1
  const frac = block.height > 0 ? Math.min(Math.max((top - block.top) / block.height, 0), 1) : 0
  emit('scroll', line + frac)
}

onMounted(() => {
  view = new EditorView({
    parent: host.value!,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        basicSetup,
        markdown({
          base: markdownLanguage,
          codeLanguages: languages,
          extensions: [{ props: [styleTags({ InlineCode: inlineCode })] }],
        }),
        EditorView.lineWrapping,
        keymap.of([
          indentWithTab,
          {
            key: 'Mod-s',
            preventDefault: true,
            run: () => {
              emit('save')
              return true
            },
          },
        ]),
        cmPlaceholder('开始写点什么吧……'),
        baseTheme,
        markdownStyle,
        themeConf.of(themeExt(props.dark)),
        readonlyConf.of(EditorState.readOnly.of(!!props.readonly)),
        EditorView.updateListener.of((u) => {
          if (u.docChanged) emit('update:modelValue', u.state.doc.toString())
        }),
        EditorView.domEventHandlers({
          scroll: () => emitScroll(),
          blur: () => emit('blur'),
          paste: (event, v) => {
            const files = imageFiles(event.clipboardData)
            if (!files.length || !canUpload()) return false
            event.preventDefault()
            const { from, to } = v.state.selection.main
            insertImages(files, from, to)
            return true
          },
          drop: (event, v) => {
            const files = imageFiles(event.dataTransfer)
            if (!files.length || !canUpload()) return false
            event.preventDefault()
            const pos =
              v.posAtCoords({ x: event.clientX, y: event.clientY }) ?? v.state.selection.main.head
            insertImages(files, pos, pos)
            return true
          },
        }),
      ],
    }),
  })
})

watch(
  () => props.modelValue,
  (val) => {
    if (view && val !== view.state.doc.toString()) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: val } })
    }
  },
)
watch(
  () => props.dark,
  (dark) => view?.dispatch({ effects: themeConf.reconfigure(themeExt(dark)) }),
)
watch(
  () => props.readonly,
  (ro) => view?.dispatch({ effects: readonlyConf.reconfigure(EditorState.readOnly.of(!!ro)) }),
)

onBeforeUnmount(() => view?.destroy())

defineExpose({
  /** 滚动到指定行（可带小数，表示行内偏移） */
  scrollToLine(line: number) {
    if (!view) return
    const doc = view.state.doc
    const n = Math.min(Math.max(Math.floor(line), 0), doc.lines - 1)
    const block = view.lineBlockAt(doc.line(n + 1).from)
    view.scrollDOM.scrollTop = block.top + block.height * (line - Math.floor(line))
  },
  /**
   * 把第 line 行（从 0 开始）滚动到顶部，用于目录跳转。
   * 不能用 scrollToLine：未渲染的行高度是估算的，直接设 scrollTop 跳到远处会有偏差；
   * scrollIntoView 由 CodeMirror 在测量实际高度后修正位置
   */
  revealLine(line: number) {
    if (!view) return
    const doc = view.state.doc
    const n = Math.min(Math.max(line, 0), doc.lines - 1)
    view.dispatch({
      effects: EditorView.scrollIntoView(doc.line(n + 1).from, { y: 'start', yMargin: 12 }),
    })
  },
  focus: () => view?.focus(),
  get scrollDOM() {
    return view?.scrollDOM ?? null
  },
})
</script>

<template>
  <div ref="host" class="md-editor" />
</template>

<style scoped>
.md-editor {
  height: 100%;
  overflow: hidden;
}
</style>
