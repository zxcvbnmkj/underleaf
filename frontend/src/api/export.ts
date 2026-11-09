import { ApiError } from './errors'

export type ExportFormat = 'pdf' | 'docx'

/**
 * 导出笔记：把当前标题和正文发给后端，返回生成的文件。
 * - pdf：后端无头 Chromium 打印渲染页，排版与预览一致
 * - docx：后端 Pandoc 转换，公式为 Word 原生公式，Mermaid 图表为图片
 *
 * 返回的是文件而不是 JSON，所以不经过 http.ts 的 request。
 */
export async function exportNote(
  format: ExportFormat,
  title: string,
  content: string,
): Promise<Blob> {
  let res: Response
  try {
    res = await fetch(`/api/v1/export/${format}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content }),
    })
  } catch {
    throw new ApiError(0, 'network_error', '无法连接导出服务，请检查网络后重试')
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    // 后端未启动时，开发服务器的代理返回 5xx 且没有 JSON
    throw new ApiError(
      res.status,
      data?.code ?? 'export_unavailable',
      data?.message ?? '导出服务暂时不可用，请稍后重试',
    )
  }
  return res.blob()
}
