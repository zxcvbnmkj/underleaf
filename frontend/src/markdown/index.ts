/**
 * Markdown 渲染的唯一配置入口。
 * 支持范围：GFM（表格、删除线、自动链接、任务列表）+ KaTeX 公式 + Shiki 代码高亮 + Mermaid。
 * 新增语法前要确认后端 Pandoc 导出 Word 时也能正确处理。
 */
import MarkdownItCtor, { type MarkdownIt } from 'markdown-it'
import * as katexModule from '@vscode/markdown-it-katex'
import * as taskListsModule from 'markdown-it-task-lists'
import type { HighlighterGeneric } from 'shiki'
import katex from 'katex'
import 'katex/dist/katex.min.css'

type Plugin<T> = (md: MarkdownIt, options?: T) => void

/** 这两个插件是 CommonJS 模块，不同打包方式下默认导出可能被包了一层或两层 default */
function unwrapPlugin<T>(mod: unknown): Plugin<T> {
  let cur = mod
  for (let i = 0; i < 3 && typeof cur !== 'function'; i++) {
    cur = (cur as { default?: unknown } | null)?.default
  }
  if (typeof cur !== 'function') throw new Error('markdown-it 插件加载失败')
  return cur as Plugin<T>
}

const katexPlugin = unwrapPlugin<{ throwOnError?: boolean; katex?: typeof katex }>(katexModule)
const taskLists = unwrapPlugin<{ enabled?: boolean; label?: boolean }>(taskListsModule)

const LANGS = [
  'javascript',
  'typescript',
  'tsx',
  'jsx',
  'vue',
  'html',
  'css',
  'scss',
  'json',
  'yaml',
  'toml',
  'markdown',
  'bash',
  'shell',
  'powershell',
  'python',
  'java',
  'kotlin',
  'go',
  'rust',
  'c',
  'cpp',
  'csharp',
  'php',
  'ruby',
  'swift',
  'sql',
  'dockerfile',
  'nginx',
  'ini',
  'xml',
  'diff',
  'latex',
]
const THEMES = { light: 'github-light', dark: 'github-dark' } as const

let highlighter: HighlighterGeneric<string, string> | null = null
let mdPromise: Promise<MarkdownIt> | null = null

function highlight(code: string, lang: string): string {
  const loaded = highlighter?.getLoadedLanguages() ?? []
  if (!highlighter || !lang || !loaded.includes(lang)) {
    return `<pre class="shiki"><code>${escapeHtml(code)}</code></pre>`
  }
  return highlighter.codeToHtml(code, { lang, themes: THEMES, defaultColor: false })
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
}

function createMarkdown(): MarkdownIt {
  // html: false —— 不渲染原始 HTML，分享页展示他人内容时避免 XSS
  const md = new MarkdownItCtor({ html: false, linkify: true, typographer: false, breaks: false })
  // 传入项目自己的 KaTeX，保证生成的 HTML 与引入的 katex.min.css 版本一致
  md.use(katexPlugin, { throwOnError: false, katex })
  md.use(taskLists, { enabled: false })

  // 给块级元素标注源码行号，用于编辑区和预览区同步滚动
  md.core.ruler.push('source_line', (state) => {
    for (const token of state.tokens) {
      if (token.map && token.block && token.nesting === 1) {
        token.attrSet('data-line', String(token.map[0]))
      }
    }
  })

  md.renderer.rules.fence = (tokens, idx) => {
    const token = tokens[idx]!
    const lang = token.info.trim().split(/\s+/)[0]?.toLowerCase() ?? ''
    const line = token.map?.[0] ?? 0
    if (lang === 'mermaid') {
      return `<div class="mermaid-block" data-line="${line}"><pre class="mermaid">${escapeHtml(token.content)}</pre></div>\n`
    }
    const label = lang ? `<span class="code-lang">${escapeHtml(lang)}</span>` : ''
    return `<div class="code-block" data-line="${line}">${label}${highlight(token.content, lang)}</div>\n`
  }
  md.renderer.rules.code_block = (tokens, idx) => {
    const token = tokens[idx]!
    return `<div class="code-block" data-line="${token.map?.[0] ?? 0}">${highlight(token.content, '')}</div>\n`
  }

  // 外部链接在新窗口打开
  const defaultLinkOpen =
    md.renderer.rules.link_open ??
    ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const href = String(tokens[idx]!.attrGet('href') ?? '')
    if (/^https?:\/\//.test(href)) {
      tokens[idx]!.attrSet('target', '_blank')
      tokens[idx]!.attrSet('rel', 'noopener noreferrer')
    }
    return defaultLinkOpen(tokens, idx, options, env, self)
  }

  return md
}

/** 获取渲染器（首次调用时加载代码高亮，之后复用） */
export function getMarkdown(): Promise<MarkdownIt> {
  mdPromise ??= (async () => {
    const md = createMarkdown()
    try {
      const { createHighlighter } = await import('shiki')
      highlighter = (await createHighlighter({
        themes: Object.values(THEMES),
        langs: LANGS,
      })) as HighlighterGeneric<string, string>
    } catch (e) {
      console.warn('代码高亮加载失败，将以纯文本显示代码', e)
    }
    return md
  })()
  return mdPromise
}

// ---------------- Mermaid ----------------

const mermaidCache = new Map<string, string>()
let mermaidPromise: Promise<typeof import('mermaid').default> | null = null
let mermaidTheme = ''

/** 渲染容器内的 mermaid 图表；相同源码的图表复用缓存，避免每次输入都闪烁 */
export async function renderMermaid(container: HTMLElement, dark: boolean) {
  const nodes = Array.from(container.querySelectorAll<HTMLElement>('pre.mermaid:not([data-done])'))
  if (!nodes.length) return

  const theme = dark ? 'dark' : 'default'
  const pending: HTMLElement[] = []
  for (const node of nodes) {
    const source = node.textContent ?? ''
    node.dataset.source = source
    const cached = mermaidCache.get(`${theme}\n${source}`)
    if (cached) {
      node.innerHTML = cached
      node.dataset.done = '1'
    } else {
      pending.push(node)
    }
  }
  if (!pending.length) return

  mermaidPromise ??= import('mermaid').then((m) => m.default)
  const mermaid = await mermaidPromise
  if (mermaidTheme !== theme) {
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme })
    mermaidTheme = theme
  }
  for (const node of pending) {
    if (!node.isConnected) continue
    const source = node.dataset.source ?? ''
    const id = `mmd-${Math.random().toString(36).slice(2)}`
    try {
      const { svg } = await mermaid.render(id, source)
      mermaidCache.set(`${theme}\n${source}`, svg)
      node.innerHTML = svg
    } catch (e) {
      // 渲染失败时 mermaid 可能在 body 上残留临时节点
      document.getElementById(`d${id}`)?.remove()
      node.innerHTML = `<div class="mermaid-error">图表语法错误：${escapeHtml(String((e as Error).message ?? e))}</div>`
    }
    node.dataset.done = '1'
  }
}
