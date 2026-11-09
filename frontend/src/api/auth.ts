import type { EmailCodePurpose, User } from '@/types'
import { http } from './http'

export interface RegisterInput {
  email: string
  code: string
  nickname: string
  password: string
}

export const authApi = {
  me: () => http.get<User>('/auth/me'),
  updateNickname: (nickname: string) => http.patch<User>('/auth/me', { nickname }),
  sendEmailCode: (email: string, purpose: EmailCodePurpose) =>
    http.post<void>('/auth/email-code', { email, purpose }),
  register: (input: RegisterInput) => http.post<User>('/auth/register', input),
  loginWithCode: (email: string, code: string) =>
    http.post<User>('/auth/login/email-code', { email, code }),
  /** account 为邮箱或昵称 */
  loginWithPassword: (account: string, password: string) =>
    http.post<User>('/auth/login/password', { account, password }),
  resetPassword: (email: string, code: string, newPassword: string) =>
    http.post<void>('/auth/password/reset', { email, code, newPassword }),
  /** 修改密码后其他设备上的登录态失效，当前设备保持登录 */
  changePassword: (oldPassword: string, newPassword: string) =>
    http.put<User>('/auth/password', { oldPassword, newPassword }),
  logout: () => http.post<void>('/auth/logout'),
}
