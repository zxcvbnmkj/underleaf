import { ApiError } from './errors'

export interface UploadedImage {
  /** 站内相对地址，如 /uploads/images/2026/11/xxx.png（不含域名，换服务器后无需修改笔记） */
  url: string
  mime: string
  size: number
}

export const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
export const IMAGE_MAX_BYTES = 10 * 1024 * 1024

/**
 * 上传图片：请求体直接是图片的二进制内容。
 * 请求体是二进制而不是 JSON，所以不经过 http.ts 的 request。
 */
export async function uploadImage(file: File): Promise<UploadedImage> {
  if (!IMAGE_TYPES.includes(file.type)) {
    throw new ApiError(415, 'image_unsupported', '只支持 PNG、JPG、GIF、WebP 格式的图片')
  }
  if (file.size > IMAGE_MAX_BYTES) {
    throw new ApiError(413, 'image_too_large', '图片不能超过 10MB')
  }
  let res: Response
  try {
    res = await fetch('/api/v1/images', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': file.type },
      body: file,
    })
  } catch {
    throw new ApiError(0, 'network_error', '图片上传失败，请检查网络后重试')
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(
      res.status,
      data?.code ?? 'upload_failed',
      data?.message ?? '图片上传服务暂时不可用，请稍后重试',
    )
  }
  return data as UploadedImage
}
