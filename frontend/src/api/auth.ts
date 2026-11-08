import type { EmailCodePurpose, User } from '@/types'
import { http } from './http'

export const authApi = {
  me: () => http.get<User>('/auth/me'),
  sendEmailCode: (email: string, purpose: EmailCodePurpose) =>
    http.post<void>('/auth/email-code', { email, purpose }),
  loginWithCode: (email: string, code: string) =>
    http.post<User>('/auth/login/email-code', { email, code }),
  loginWithPassword: (email: string, password: string) =>
    http.post<User>('/auth/login/password', { email, password }),
  resetPassword: (email: string, code: string, newPassword: string) =>
    http.post<void>('/auth/password/reset', { email, code, newPassword }),
  /** 已有密码时需要提供 oldPassword */
  changePassword: (newPassword: string, oldPassword?: string) =>
    http.put<User>('/auth/password', { oldPassword, newPassword }),
  logout: () => http.post<void>('/auth/logout'),
}
