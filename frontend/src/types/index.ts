export interface User {
  id: number
  email: string
  /** 通过验证码注册的用户默认没有密码 */
  hasPassword: boolean
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
  updatedAt: string
}

export interface Note extends NoteMeta {
  content: string
}

export interface SharedNote {
  title: string
  content: string
  updatedAt: string
}

export type EmailCodePurpose = 'login' | 'reset_password'
