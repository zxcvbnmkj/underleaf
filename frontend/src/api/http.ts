import { ApiError } from './errors'

export { ApiError }

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  if (USE_MOCK) {
    // 按需加载，正式构建（VITE_USE_MOCK 不为 true）时不会打包 mock 代码
    const { mockRequest } = await import('./mock')
    return mockRequest<T>(method, path, body)
  }

  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, {
      method,
      credentials: 'include',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'network_error', '网络连接失败，请检查网络')
  }

  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(
      res.status,
      data?.code ?? 'unknown_error',
      data?.message ?? `请求失败（${res.status}）`,
      data?.detail,
    )
  }
  return data as T
}

export const http = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body ?? {}),
  delete: <T>(path: string) => request<T>('DELETE', path),
}
