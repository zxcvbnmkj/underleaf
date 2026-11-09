export interface Segment {
  text: string
  hit: boolean
}

/** 按空格拆分搜索词，去重并去掉空串 */
export function splitTerms(query: string): string[] {
  return [...new Set(query.trim().split(/\s+/).filter(Boolean))]
}

/**
 * 把文本按关键词切成片段，hit 为 true 的是命中部分（不区分大小写）。
 * 交给模板逐段渲染，不拼 HTML，避免注入。
 */
export function highlight(text: string, terms: string[]): Segment[] {
  if (!text || !terms.length) return [{ text, hit: false }]
  // 长词优先，避免「ab」先匹配导致「abc」只高亮一半
  const escaped = [...terms]
    .sort((a, b) => b.length - a.length)
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const re = new RegExp(`(${escaped.join('|')})`, 'gi')
  // split 带捕获组时，奇数下标是匹配到的部分
  return text
    .split(re)
    .map((part, i) => ({ text: part, hit: i % 2 === 1 }))
    .filter((s) => s.text)
}
