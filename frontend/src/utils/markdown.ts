/** 正文是否以一级标题开头（此时页面不再单独显示标题，避免重复） */
export function startsWithH1(content: string): boolean {
  return /^\s*#\s/.test(content)
}
