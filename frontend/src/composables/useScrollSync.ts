interface Anchor {
  line: number
  top: number
}

/**
 * 编辑区与预览区的同步滚动。
 * 预览区中的块级元素带有 data-line（源码行号），据此在「行号」与「预览滚动位置」之间做分段线性插值。
 */
export function createScrollSync(getPane: () => HTMLElement | null | undefined) {
  let anchors: Anchor[] | null = null

  function build(): Anchor[] {
    const pane = getPane()
    if (!pane) return []
    const paneTop = pane.getBoundingClientRect().top - pane.scrollTop
    const raw = Array.from(pane.querySelectorAll<HTMLElement>('[data-line]')).map((el) => ({
      line: Number(el.dataset.line),
      top: el.getBoundingClientRect().top - paneTop,
    }))
    raw.sort((a, b) => a.line - b.line || a.top - b.top)
    // 只保留行号和位置都严格递增的锚点，保证插值单调
    const result: Anchor[] = [{ line: 0, top: 0 }]
    for (const a of raw) {
      const last = result[result.length - 1]!
      if (a.line > last.line && a.top > last.top) result.push(a)
    }
    return result
  }

  const getAnchors = () => (anchors ??= build())

  return {
    /** 预览内容或尺寸变化后调用 */
    invalidate() {
      anchors = null
    },

    /** 编辑区滚动到 line（可带小数）时，预览区应滚动到的位置 */
    previewTopForLine(line: number, totalLines: number): number {
      const pane = getPane()
      if (!pane) return 0
      const list = getAnchors()
      const end: Anchor = {
        line: Math.max(totalLines, list[list.length - 1]!.line + 1),
        top: pane.scrollHeight,
      }
      for (let i = 0; i < list.length; i++) {
        const a = list[i]!
        const b = list[i + 1] ?? end
        if (line < b.line || i === list.length - 1) {
          const t = b.line === a.line ? 0 : (line - a.line) / (b.line - a.line)
          return a.top + Math.min(Math.max(t, 0), 1) * (b.top - a.top)
        }
      }
      return 0
    },

    /** 预览区滚动到 top 时，编辑区应滚动到的行号（可带小数） */
    lineForPreviewTop(top: number, totalLines: number): number {
      const pane = getPane()
      if (!pane) return 0
      const list = getAnchors()
      const end: Anchor = {
        line: Math.max(totalLines, list[list.length - 1]!.line + 1),
        top: pane.scrollHeight,
      }
      for (let i = 0; i < list.length; i++) {
        const a = list[i]!
        const b = list[i + 1] ?? end
        if (top < b.top || i === list.length - 1) {
          const t = b.top === a.top ? 0 : (top - a.top) / (b.top - a.top)
          return a.line + Math.min(Math.max(t, 0), 1) * (b.line - a.line)
        }
      }
      return 0
    },
  }
}
