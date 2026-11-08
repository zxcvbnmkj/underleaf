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
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  /** 滚动时报告顶部可见位置：行号（从 0 开始）+ 该行内的偏移比例 */
  scroll: [line: number]
  save: []
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
  '.cm-activeLine': { backgroundColor: 'var(--ul-bg-soft)' },
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
    { tag: tags.strong, fontWeight: '700', color: 'var(--ul-text)' },
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

function themeExt(dark: boolean) {
  return dark ? oneDark : lightTheme
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
        EditorView.domEventHandlers({ scroll: () => emitScroll() }),
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
