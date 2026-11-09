/** 文件名中不允许出现的字符（按最严格的 Windows 规则） */
const ILLEGAL_FILENAME_CHARS = /[\\/:*?"<>|\u0000-\u001f]/g

export function safeFilename(name: string, ext: string): string {
  const base = name
    .replace(ILLEGAL_FILENAME_CHARS, '_')
    .trim()
    .replace(/^\.+|\.+$/g, '')
  return `${base || 'note'}.${ext}`
}

/** 触发浏览器下载一个 Blob */
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  // 部分浏览器在 click 之后才开始读取，稍后再释放
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}
