/**
 * 复制文本到剪贴板，成功返回 true。
 *
 * navigator.clipboard 只在安全上下文（HTTPS 或 localhost）中可用；
 * 线上目前通过 http://IP:端口 访问，需要退回到 execCommand('copy')。
 */
export async function copyText(text: string): Promise<boolean> {
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 权限被拒等情况，继续尝试旧方法
    }
  }
  return legacyCopy(text)
}

function legacyCopy(text: string): boolean {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  // 放在视口外，避免页面闪动和滚动；不能用 display: none，否则无法选中
  textarea.style.position = 'fixed'
  textarea.style.top = '-9999px'
  textarea.style.opacity = '0'
  // 弹窗（NModal）会把焦点限制在弹窗内，插到当前焦点元素所在的容器中才能选中
  const container = document.activeElement?.closest('[role="dialog"]') ?? document.body
  container.appendChild(textarea)
  const previousFocus = document.activeElement as HTMLElement | null
  textarea.select()
  textarea.setSelectionRange(0, text.length)
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  container.removeChild(textarea)
  previousFocus?.focus?.()
  return ok
}
