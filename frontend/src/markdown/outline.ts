import type { MarkdownIt } from 'markdown-it'

export interface OutlineItem {
  /** 标题级别：1 ~ maxLevel */
  level: number
  /** 纯文本标题（去掉了粗体、链接等 Markdown 标记） */
  text: string
  /** 标题所在的源码行号（从 0 开始），与预览中的 data-line 一致 */
  line: number
}

/**
 * 从 Markdown 中提取目录。
 * 与预览使用同一个 markdown-it 解析，代码块中的 # 不会被当成标题，
 * 「===」「---」形式的标题也能识别。
 */
export function extractOutline(md: MarkdownIt, source: string, maxLevel = 3): OutlineItem[] {
  const tokens = md.parse(source, {})
  const items: OutlineItem[] = []
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i]!
    if (t.type !== 'heading_open' || !t.map) continue
    const level = Number(t.tag.slice(1))
    if (level > maxLevel) continue
    const inline = tokens[i + 1]
    const text = (inline?.children ?? [])
      .filter((c) => c.type === 'text' || c.type === 'code_inline' || c.type === 'math_inline')
      .map((c) => c.content)
      .join('')
      .trim()
    if (text) items.push({ level, text, line: t.map[0] })
  }
  return items
}
