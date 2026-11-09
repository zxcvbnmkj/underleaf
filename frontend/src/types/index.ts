export interface User {
  id: number
  email: string
  /** 全局唯一，可以代替邮箱登录 */
  nickname: string
}

export interface Folder {
  id: number
  name: string
  parentId: number | null
}

/** 笔记元信息（不含正文），用于文件夹树 */
export interface NoteMeta {
  id: number
  title: string
  folderId: number | null
  isPublic: boolean
  publicId: string
  version: number
  createdAt: string
  updatedAt: string
}

export interface Note extends NoteMeta {
  content: string
}

export interface SharedNote {
  title: string
  content: string
  createdAt: string
  updatedAt: string
  /** 只公开昵称，不公开邮箱 */
  author: { nickname: string }
}

export type EmailCodePurpose = 'register' | 'login' | 'reset_password'

/** 个人访问令牌（Git 同步时作为密码使用） */
export interface AccessToken {
  id: number
  name: string
  /** 令牌末尾几个字符，帮助辨认 */
  lastChars: string
  expiresAt: string | null
  lastUsedAt: string | null
  createdAt: string
}

/** 创建令牌时的返回值，明文令牌只返回这一次 */
export interface CreatedAccessToken extends AccessToken {
  token: string
}

export interface GitInfo {
  /** clone 地址的路径部分，前端拼上当前网站的地址 */
  clonePath: string
  /** 建议的用户名（可以随便填，服务器只校验令牌） */
  username: string
}
