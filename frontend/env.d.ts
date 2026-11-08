/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 为 true 时使用浏览器本地的 mock 后端 */
  readonly VITE_USE_MOCK?: string
}

declare module 'markdown-it-task-lists' {
  import type { MarkdownIt } from 'markdown-it'
  const plugin: (md: MarkdownIt, options?: { enabled?: boolean; label?: boolean }) => void
  export default plugin
}
