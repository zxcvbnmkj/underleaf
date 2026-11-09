import type { AccessToken, CreatedAccessToken, GitInfo } from '@/types'
import { http } from './http'

export const gitApi = {
  info: () => http.get<GitInfo>('/git/info'),
  listTokens: () => http.get<AccessToken[]>('/tokens'),
  /** expiresInDays 为 null 表示永不过期 */
  createToken: (name: string, expiresInDays: number | null) =>
    http.post<CreatedAccessToken>('/tokens', { name, expiresInDays }),
  revokeToken: (id: number) => http.delete<void>(`/tokens/${id}`),
}
