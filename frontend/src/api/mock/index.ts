/**
 * 浏览器内的 mock 后端：按真实接口的路径和格式返回数据，
 * 数据存放在 localStorage 中，同一浏览器的多个标签页共享（可以用来测试冲突检测）。
 */
import type { EmailCodePurpose, Folder, Note, NoteMeta, User } from '@/types'
import { ApiError } from '../errors'
import { DRAFT_CONTENT, WELCOME_CONTENT } from './seed'
import { MOCK_CODE, MOCK_DEMO_ACCOUNT } from './constants'

const DB_KEY = 'underleaf-mock-db'
const SESSION_KEY = 'underleaf-mock-session'
const LATENCY = 200

interface MockUser {
  id: number
  email: string
  password: string | null
}
interface MockCode {
  email: string
  purpose: EmailCodePurpose
  sentAt: number
  attempts: number
}
interface DB {
  seq: number
  users: MockUser[]
  folders: (Folder & { userId: number })[]
  notes: (Note & { userId: number })[]
  codes: MockCode[]
  loginFailures: Record<string, { count: number; lockedUntil: number }>
}

let memoryDB: DB | null = null
let memorySession: number | null = null

function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function storageSet(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    /* 隐私模式等场景下退化为内存存储 */
  }
}

function loadDB(): DB {
  const raw = storageGet(DB_KEY)
  if (raw) {
    try {
      return JSON.parse(raw) as DB
    } catch {
      /* 数据损坏时重建 */
    }
  }
  if (memoryDB) return memoryDB
  const db: DB = { seq: 0, users: [], folders: [], notes: [], codes: [], loginFailures: {} }
  createUser(db, MOCK_DEMO_ACCOUNT.email, MOCK_DEMO_ACCOUNT.password)
  saveDB(db)
  return db
}
function saveDB(db: DB) {
  memoryDB = db
  storageSet(DB_KEY, JSON.stringify(db))
}

function getSession(): number | null {
  const raw = storageGet(SESSION_KEY)
  return raw ? Number(raw) : memorySession
}
function setSession(userId: number | null) {
  memorySession = userId
  storageSet(SESSION_KEY, userId === null ? null : String(userId))
}

const now = () => new Date().toISOString()

function randomId(len = 10) {
  const alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  const bytes = crypto.getRandomValues(new Uint8Array(len))
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('')
}

function createUser(db: DB, email: string, password: string | null): MockUser {
  const user = { id: ++db.seq, email, password }
  db.users.push(user)
  // 新用户附带示例笔记
  const folder = { id: ++db.seq, name: '入门', parentId: null, userId: user.id }
  const sub = { id: ++db.seq, name: '读书', parentId: folder.id, userId: user.id }
  db.folders.push(folder, sub)
  addNote(db, user.id, '欢迎使用 Underleaf', folder.id, WELCOME_CONTENT)
  addNote(db, user.id, '读书笔记', sub.id, DRAFT_CONTENT)
  return user
}

function addNote(db: DB, userId: number, title: string, folderId: number | null, content = '') {
  const note = {
    id: ++db.seq,
    title,
    folderId,
    content,
    isPublic: false,
    publicId: randomId(),
    version: 1,
    updatedAt: now(),
    userId,
  }
  db.notes.push(note)
  return note
}

const toUser = (u: MockUser): User => ({ id: u.id, email: u.email, hasPassword: !!u.password })
const toFolder = ({ id, name, parentId }: Folder): Folder => ({ id, name, parentId })
const toMeta = (n: Note): NoteMeta => ({
  id: n.id,
  title: n.title,
  folderId: n.folderId,
  isPublic: n.isPublic,
  publicId: n.publicId,
  version: n.version,
  updatedAt: n.updatedAt,
})
const toNote = (n: Note): Note => ({ ...toMeta(n), content: n.content })

const fail = (status: number, code: string, message: string): never => {
  throw new ApiError(status, code, message)
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
function checkEmail(email: unknown): string {
  if (typeof email !== 'string' || !EMAIL_RE.test(email.trim()))
    fail(422, 'invalid_email', '邮箱格式不正确')
  return (email as string).trim().toLowerCase()
}
function checkPassword(pw: unknown) {
  if (typeof pw !== 'string' || pw.length < 8) fail(422, 'weak_password', '密码至少 8 位')
}

function consumeCode(db: DB, email: string, purpose: EmailCodePurpose, code: string) {
  const rec = db.codes.find((c) => c.email === email && c.purpose === purpose)
  if (!rec || Date.now() - rec.sentAt > 5 * 60_000)
    fail(400, 'code_expired', '验证码已过期，请重新获取')
  if (code !== MOCK_CODE) {
    rec!.attempts++
    if (rec!.attempts >= 5) db.codes = db.codes.filter((c) => c !== rec)
    saveDB(db)
    fail(400, 'code_invalid', '验证码错误')
  }
  db.codes = db.codes.filter((c) => c !== rec)
}

type Body = Record<string, unknown>
type Handler = (ctx: { db: DB; body: Body; params: string[]; userId: number | null }) => unknown

function requireUser(userId: number | null): number {
  if (userId === null) fail(401, 'unauthorized', '请先登录')
  return userId!
}
function ownFolder(db: DB, userId: number, id: number) {
  return (
    db.folders.find((f) => f.id === id && f.userId === userId) ??
    fail(404, 'not_found', '文件夹不存在')
  )
}
function ownNote(db: DB, userId: number, id: number) {
  return (
    db.notes.find((n) => n.id === id && n.userId === userId) ?? fail(404, 'not_found', '笔记不存在')
  )
}

const routes: [string, RegExp, Handler][] = [
  // ---------- 认证 ----------
  [
    'GET',
    /^\/auth\/me$/,
    ({ db, userId }) => {
      const uid = requireUser(userId)
      const user = db.users.find((u) => u.id === uid) ?? fail(401, 'unauthorized', '请先登录')
      return toUser(user)
    },
  ],
  [
    'POST',
    /^\/auth\/email-code$/,
    ({ db, body }) => {
      const email = checkEmail(body.email)
      const purpose = body.purpose as EmailCodePurpose
      const prev = db.codes.find((c) => c.email === email && c.purpose === purpose)
      if (prev && Date.now() - prev.sentAt < 60_000)
        fail(429, 'too_frequent', '发送太频繁，请稍后再试')
      db.codes = db.codes.filter((c) => c !== prev)
      db.codes.push({ email, purpose, sentAt: Date.now(), attempts: 0 })
      saveDB(db)
    },
  ],
  [
    'POST',
    /^\/auth\/login\/email-code$/,
    ({ db, body }) => {
      const email = checkEmail(body.email)
      consumeCode(db, email, 'login', String(body.code ?? ''))
      const user = db.users.find((u) => u.email === email) ?? createUser(db, email, null)
      saveDB(db)
      setSession(user.id)
      return toUser(user)
    },
  ],
  [
    'POST',
    /^\/auth\/login\/password$/,
    ({ db, body }) => {
      const email = checkEmail(body.email)
      const lock = db.loginFailures[email]
      if (lock && lock.lockedUntil > Date.now()) {
        const minutes = Math.ceil((lock.lockedUntil - Date.now()) / 60_000)
        fail(423, 'account_locked', `密码错误次数过多，请 ${minutes} 分钟后再试，或使用验证码登录`)
      }
      const user = db.users.find((u) => u.email === email)
      if (!user || !user.password || user.password !== body.password) {
        const rec = (db.loginFailures[email] ??= { count: 0, lockedUntil: 0 })
        rec.count++
        if (rec.count >= 5) {
          rec.count = 0
          rec.lockedUntil = Date.now() + 15 * 60_000
        }
        saveDB(db)
        fail(401, 'invalid_credentials', '邮箱或密码错误')
      }
      delete db.loginFailures[email]
      saveDB(db)
      setSession(user!.id)
      return toUser(user!)
    },
  ],
  [
    'POST',
    /^\/auth\/password\/reset$/,
    ({ db, body }) => {
      const email = checkEmail(body.email)
      checkPassword(body.newPassword)
      consumeCode(db, email, 'reset_password', String(body.code ?? ''))
      const user =
        db.users.find((u) => u.email === email) ?? fail(400, 'code_invalid', '验证码错误')
      user.password = body.newPassword as string
      delete db.loginFailures[email]
      saveDB(db)
    },
  ],
  [
    'PUT',
    /^\/auth\/password$/,
    ({ db, body, userId }) => {
      const user = db.users.find((u) => u.id === requireUser(userId))!
      if (user.password && user.password !== body.oldPassword)
        fail(400, 'wrong_password', '原密码错误')
      checkPassword(body.newPassword)
      user.password = body.newPassword as string
      saveDB(db)
      return toUser(user)
    },
  ],
  [
    'POST',
    /^\/auth\/logout$/,
    () => {
      setSession(null)
    },
  ],

  // ---------- 文件夹 ----------
  [
    'GET',
    /^\/folders$/,
    ({ db, userId }) => {
      const uid = requireUser(userId)
      return db.folders.filter((f) => f.userId === uid).map(toFolder)
    },
  ],
  [
    'POST',
    /^\/folders$/,
    ({ db, body, userId }) => {
      const uid = requireUser(userId)
      const parentId = (body.parentId as number | null) ?? null
      if (parentId !== null) ownFolder(db, uid, parentId)
      const folder = {
        id: ++db.seq,
        name: String(body.name || '新建文件夹'),
        parentId,
        userId: uid,
      }
      db.folders.push(folder)
      saveDB(db)
      return toFolder(folder)
    },
  ],
  [
    'PATCH',
    /^\/folders\/(\d+)$/,
    ({ db, body, params, userId }) => {
      const uid = requireUser(userId)
      const folder = ownFolder(db, uid, Number(params[0]))
      if (typeof body.name === 'string') folder.name = body.name
      if ('parentId' in body) {
        const parentId = body.parentId as number | null
        // 不能移动到自己或自己的子孙文件夹下
        for (let p = parentId; p !== null; p = ownFolder(db, uid, p).parentId) {
          if (p === folder.id) fail(400, 'invalid_move', '不能移动到自身的子文件夹中')
        }
        folder.parentId = parentId
      }
      saveDB(db)
      return toFolder(folder)
    },
  ],
  [
    'DELETE',
    /^\/folders\/(\d+)$/,
    ({ db, params, userId }) => {
      const uid = requireUser(userId)
      const root = ownFolder(db, uid, Number(params[0]))
      const ids = new Set([root.id])
      let grew = true
      while (grew) {
        grew = false
        for (const f of db.folders) {
          if (f.parentId !== null && ids.has(f.parentId) && !ids.has(f.id)) {
            ids.add(f.id)
            grew = true
          }
        }
      }
      db.folders = db.folders.filter((f) => !ids.has(f.id))
      db.notes = db.notes.filter((n) => n.folderId === null || !ids.has(n.folderId))
      saveDB(db)
    },
  ],

  // ---------- 笔记 ----------
  [
    'GET',
    /^\/notes$/,
    ({ db, userId }) => {
      const uid = requireUser(userId)
      return db.notes.filter((n) => n.userId === uid).map(toMeta)
    },
  ],
  [
    'POST',
    /^\/notes$/,
    ({ db, body, userId }) => {
      const uid = requireUser(userId)
      const folderId = (body.folderId as number | null) ?? null
      if (folderId !== null) ownFolder(db, uid, folderId)
      const note = addNote(db, uid, String(body.title || '未命名笔记'), folderId)
      saveDB(db)
      return toNote(note)
    },
  ],
  [
    'GET',
    /^\/notes\/(\d+)$/,
    ({ db, params, userId }) => toNote(ownNote(db, requireUser(userId), Number(params[0]))),
  ],
  [
    'PATCH',
    /^\/notes\/(\d+)$/,
    ({ db, body, params, userId }) => {
      const uid = requireUser(userId)
      const note = ownNote(db, uid, Number(params[0]))
      if (typeof body.title === 'string') note.title = body.title.trim() || '未命名笔记'
      if ('folderId' in body) {
        const folderId = body.folderId as number | null
        if (folderId !== null) ownFolder(db, uid, folderId)
        note.folderId = folderId
      }
      if (typeof body.isPublic === 'boolean') note.isPublic = body.isPublic
      note.updatedAt = now()
      saveDB(db)
      return toMeta(note)
    },
  ],
  [
    'PUT',
    /^\/notes\/(\d+)\/content$/,
    ({ db, body, params, userId }) => {
      const note = ownNote(db, requireUser(userId), Number(params[0]))
      if (body.version !== note.version) fail(409, 'version_conflict', '笔记已在其他设备上修改')
      note.content = String(body.content ?? '')
      note.version++
      note.updatedAt = now()
      saveDB(db)
      return toMeta(note)
    },
  ],
  [
    'DELETE',
    /^\/notes\/(\d+)$/,
    ({ db, params, userId }) => {
      const note = ownNote(db, requireUser(userId), Number(params[0]))
      db.notes = db.notes.filter((n) => n !== note)
      saveDB(db)
    },
  ],

  // ---------- 公开分享 ----------
  [
    'GET',
    /^\/share\/([\w-]+)$/,
    ({ db, params }) => {
      const note = db.notes.find((n) => n.publicId === params[0] && n.isPublic)
      if (!note) fail(404, 'not_found', '分享不存在或已关闭')
      return { title: note!.title, content: note!.content, updatedAt: note!.updatedAt }
    },
  ],
]

export async function mockRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  await new Promise((r) => setTimeout(r, LATENCY))
  for (const [m, re, handler] of routes) {
    const match = m === method ? re.exec(path) : null
    if (!match) continue
    const result = handler({
      db: loadDB(),
      body: (body ?? {}) as Body,
      params: match.slice(1),
      userId: getSession(),
    })
    // 返回深拷贝，避免调用方修改 mock 数据
    return (result === undefined ? undefined : JSON.parse(JSON.stringify(result))) as T
  }
  throw new ApiError(404, 'not_found', `mock 未实现：${method} ${path}`)
}
