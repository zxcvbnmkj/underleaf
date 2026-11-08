# 在线 MarkDown 的知识管理平台
## 来源
- 借鉴了 overleaf 这种在线的 latex 编辑器，左侧编辑右侧渲染
- 线上托管笔记，避免跨设备进度不同步，需要传来出去的问题，也不怕丢失，便于管理

## 功能
- 笔记按**文件夹树**组织
- 左侧编辑、右侧实时预览，支持同步滚动
- 笔记支持网页链接分享（**只读**）、下载为 PDF、下载为 Word
- 自动保存，多设备编辑同一篇时检测冲突，不静默覆盖
- 注册需要邮箱验证码 + 昵称 + 密码；登录支持「邮箱 / 昵称 + 密码」和「邮箱 + 验证码」；忘记密码可以用验证码登录或重置密码
- （规划中）通过 Git 在本地与网页之间同步笔记，详见「Git 同步」

### 暂不考虑
- 图片上传（因此暂不引入对象存储）
- 微信登录
- 历史版本快照
- 多人实时协同编辑

## 技术选型

| 层 | 选型 | 说明 |
|---|---|---|
| 后端框架 | FastAPI + Pydantic v2 | |
| ORM / 迁移 | SQLAlchemy 2.0（async）+ Alembic | |
| 数据库 | MySQL 8（驱动 aiomysql） | 复用服务器已有实例（库名 `underleaf`）；8.0 起支持递归 CTE 和 ngram 中文全文索引 |
| 缓存 | Redis（redis-py asyncio） | 存验证码、发送冷却等短期数据，靠 TTL 自动过期 |
| 认证 | 邮箱验证码 / 账号密码 + JWT（httpOnly Cookie） | 密码用 Argon2 哈希（pwdlib）；邮件通过 SMTP 发送（aiosmtplib） |
| 导出 | Playwright（PDF）、Pandoc（Word） | PDF 由后端无头 Chromium 打印前端打印页，用户直接下载，与用户使用的浏览器无关；后端接入前暂用浏览器打印过渡 |
| 后端工具 | PDM + ruff + pyright + pytest | |
| 前端 | Vue3 + Vite + TypeScript + Pinia + Vue Router | |
| 编辑器 | CodeMirror 6 | 比 Monaco 轻，移动端友好 |
| 渲染 | markdown-it + KaTeX + Shiki + Mermaid | |
| UI 库 | Naive UI | 对 TS 友好 |
| 部署 | Docker Compose + Nginx | |

## 关键设计

### 渲染一致性
- **预览与 PDF 同源**：PDF 由前端打印页 `/print/{noteId}` 打印而来，该页和编辑区预览、分享页使用同一个 `MarkdownPreview` 组件和 `markdown.css`，优化渲染效果后 PDF 自动跟着变，无需单独修改
- **Word 走 Pandoc**：公式可转为 Word 原生公式
- **语法范围收窄**：只支持 GFM + KaTeX 公式 + 代码高亮 + Mermaid。markdown-it 插件统一放在 `frontend/src/markdown/` 中配置，新增语法前要确认 Pandoc 也能正确导出

### PDF 导出：打印页
- **流程**：点击“导出 PDF” → 先保存本地修改（打印页读的是服务器数据）→ 新标签页打开 `/print/{noteId}?auto=1` → 渲染完成后自动弹出打印对话框，用户选“另存为 PDF” → 打印结束后标签页自动关闭
- **打印页职责**：固定浅色主题；按 A4 纸宽排版；`<title>` 设为笔记标题（即默认文件名）；正文不以一级标题开头时补上标题
- **就绪信号**：Markdown、Mermaid、字体、图片全部渲染完成后，在 `<html>` 上设置 `data-export-ready="true"`（失败为 `"error"`），浏览器打印和 Playwright 都以此为准，避免打出半成品
- **打印样式**：集中在 `markdown.css` 的 `@page` 和 `@media print` 中——代码自动换行而非横向滚动、表格铺满、过宽的图表缩放、标题不落在页尾、代码块/公式/图表/表格行尽量不被分页切开
- **改渲染时需要注意**：普通样式调整不用管导出；只有以下情况要同步处理——
  - 新增可能比纸宽或不宜被切开的块 → 在 `@media print` 中补规则
  - 新增异步渲染步骤（类似 Mermaid）→ 必须在 `MarkdownPreview` 触发 `rendered` 之前完成，否则打印时还没画出来
  - 新增颜色 → 浅色主题下也要清晰（打印固定浅色）
  - 新增语法 → 还要确认 Pandoc 能导出 Word（Word 不复用前端渲染）
- **已知限制**：浏览器打印对话框默认带页眉页脚（日期、网址），需用户在“更多设置”中取消勾选；不同浏览器输出略有差异
- **最终方案**：后端用 Chromium 生成 PDF 后直接下载，见下一节。浏览器打印只是后端接入前的过渡方案

### PDF 导出：后端 Chromium 直接生成（已确定）

用户点击「导出 PDF」直接下载文件，不弹打印对话框、不带页眉页脚。PDF 在服务器上生成，和用户用什么浏览器无关，Chrome、Safari、Firefox、手机浏览器、微信内置浏览器都一样能下载。

#### 流程
1. 前端先保存未保存的修改，然后请求 `GET /api/v1/notes/{id}/export.pdf`
2. 后端校验登录态和笔记归属，用 Playwright 控制服务器上的无头 Chromium 打开前端打印页 `/print/{id}`
3. 等待 `html[data-export-ready="true"]`（出现 `"error"` 或超时则返回失败）
4. 调用 `page.pdf({ preferCSSPageSize: true, printBackground: true })`，纸张和页边距由 `markdown.css` 的 `@page` 决定
5. 以附件形式返回，前端拿到文件后触发下载

打印页、Markdown 渲染、打印样式都复用前端现有代码，后端不参与排版，所以预览和 PDF 始终一致。

#### 实现要点
- **只用 Chromium**：Playwright 支持 Chromium / Firefox / WebKit 三种内核，但只有 Chromium 能生成 PDF。这里的 Chromium 只是服务器上的排版工具，用户看不到它
- **登录态**：后端把当前请求的登录 Cookie 设置到 Playwright 的浏览器上下文中，打印页里调用接口时就是该用户本人，无需额外的令牌
- **打印页地址**：通过配置项 `EXPORT_RENDER_URL` 指定 Chromium 访问前端的内网地址（如 `http://nginx`），不经过公网
- **复用浏览器**：应用启动时启动一个 Chromium 并常驻，每次导出新建一个浏览器上下文、用完关闭；不要每次都重新启动 Chromium（启动一次要 1 秒以上）
- **限流**：用信号量限制同时导出的数量（如 2 个），超出的排队；单次导出 30 秒超时；同一用户限制频率，防止刷接口
- **文件名**：笔记标题 + `.pdf`，响应头 `Content-Disposition: attachment; filename*=UTF-8''<URL 编码后的标题>.pdf`，保证中文文件名在各浏览器都正常
- **中文字体**：服务器必须安装中文字体（如 Noto Sans CJK / Noto Serif CJK）和 emoji 字体（Noto Color Emoji），否则 PDF 中的中文会显示成方块
- **前端交互**：导出期间按钮显示加载状态，避免重复点击；失败时给出明确提示

#### 部署
- 推荐直接使用 Playwright 官方 Python 镜像作为后端基础镜像，已包含 Chromium 及其系统依赖，再额外安装中文字体
- 不用镜像时：`pip install playwright` 后执行 `playwright install --with-deps chromium`
- 资源占用：常驻的 Chromium 约 100～200MB 内存，每个导出任务额外占用几十到一百多 MB，通常几秒内完成

### 多设备防覆盖
- 笔记带 `version` 字段，保存时校验版本（乐观锁）：`UPDATE ... SET version = version + 1 WHERE id = ? AND version = ?`，影响行数为 0 即冲突，提示用户而不直接覆盖
- 前端自动保存做防抖处理

### 文件夹树
- `folder` 表通过 `parent_id` 自关联形成树，笔记通过 `folder_id` 归属到文件夹
- 树的层级不深，整棵树一次性下发，由前端组装

### 只读分享
- 笔记带 `is_public` 开关，打开后可以通过 `/s/{public_id}` 公开访问只读渲染页，链接永久有效
- `public_id` 是建笔记时生成的随机字符串（如 nanoid），不能用自增 id，否则别人可以通过遍历 id 访问所有公开笔记
- 关闭开关后链接立即失效，再次打开后恢复为原链接

### 登录
- 一个邮箱对应一个用户；昵称也全局唯一（不区分大小写）
- **注册**：邮箱 → 收到 6 位验证码 → 填写验证码、昵称、密码 → 注册并登录。邮箱或昵称已被占用时提示
- **登录（三种方式，登录的是同一个账号）**：
  - 邮箱 + 密码
  - 昵称 + 密码（与上一种共用一个输入框，后端根据是否包含 `@` 区分，因此昵称不能包含 `@`）
  - 邮箱 + 验证码（邮箱未注册时提示先注册，不自动注册）
- **忘记密码**：用验证码登录，或通过邮箱验证码重置密码
- **昵称规则**：2～20 个字符，允许中文、字母、数字、`_`、`-`，不能包含 `@` 和空格；注册后可以修改
- **密码**：Argon2 哈希存储，至少 8 位；登录失败统一提示「账号或密码错误」
- **不做账号锁定**：防暴力破解交给 Nginx 按 IP 对登录接口限流（如每分钟 10 次），不在数据库中记录失败次数
- **验证码**：存 Redis（只存哈希），不建表
  - 有效期 5 分钟（Redis TTL 自动过期），同一邮箱 60 秒内只能发送一次，连续输错 5 次作废，验证成功后立即删除
  - 区分用途：注册 / 登录 / 重置密码，不能混用
  - 不能放在后端进程内存中：重启会丢失，多 worker 部署时发码和验码可能落在不同进程
- **登录态**：较长有效期的 JWT（如 30 天），放在 httpOnly Cookie 中；JWT 中带 `token_version`，修改或重置密码时加 1，其他设备上的登录态全部失效

### 数据库表
- 统一约定：主键 `BIGINT` 自增；时间用 `DATETIME(3)` 存 UTC；字符集 `utf8mb4` + `utf8mb4_0900_ai_ci`（比较名字时不区分大小写，与 Windows / macOS 文件系统一致，利于 Git 同步）
- 删除为物理删除，不做回收站

**`user`**
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| email | VARCHAR(254) | 唯一 |
| nickname | VARCHAR(32) | 唯一 |
| password_hash | VARCHAR(255) | 必填 |
| token_version | INT | 默认 0，改密码时加 1 |
| content_rev | BIGINT | 默认 0，该用户的笔记或文件夹有任何变动就加 1，供 Git 同步判断是否需要生成快照 |
| created_at / updated_at | DATETIME(3) | |

**`folder`**
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| user_id | BIGINT | 外键 → user，级联删除 |
| parent_id | BIGINT NULL | 外键 → folder，级联删除；NULL 表示在根目录 |
| parent_key | BIGINT | VIRTUAL 生成列 `IFNULL(parent_id, 0)`，由数据库自动维护 |
| name | VARCHAR(255) | |
| created_at / updated_at | DATETIME(3) | |

唯一索引 `(user_id, parent_key, name)`。

**`note`**
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| user_id | BIGINT | 外键 → user，级联删除 |
| folder_id | BIGINT NULL | 外键 → folder，级联删除；NULL 表示在根目录 |
| folder_key | BIGINT | VIRTUAL 生成列 `IFNULL(folder_id, 0)` |
| title | VARCHAR(255) | |
| content | MEDIUMTEXT | 正文 |
| version | INT | 乐观锁版本号，默认 1 |
| is_public | BOOLEAN | 分享开关，默认关闭 |
| public_id | CHAR(12) | 唯一，建笔记时随机生成 |
| created_at / updated_at | DATETIME(3) | |

唯一索引 `(user_id, folder_key, title)`。

- **为什么用生成列**：MySQL 中 NULL 与 NULL 不相等，直接在 `(user_id, parent_id, name)` 上建唯一索引时，根目录下的同名限制会失效。`parent_id` 不能直接用 0 代替 NULL，因为外键要求它指向真实存在的文件夹；生成列既保留外键和级联删除，又让唯一索引在根目录生效
- **生成列必须是 VIRTUAL**：MySQL 不允许 STORED 生成列的基础列带 `ON DELETE CASCADE` 外键，建表会直接报错（已实测）
- **名称限制**：标题和文件夹名按 UTF-8 不超过 240 字节（约 80 个汉字），不能包含 `/ \ : * ? " < > |`，不能是 `.` 或 `..`
- **文件夹最多 10 层**：MySQL 级联删除最多连锁 15 层，超过会报错
- **Git 同步（第二版）再建**：`access_token`（id, user_id, name, token_hash 唯一, expires_at, last_used_at, revoked_at, created_at）和 `git_repo`（user_id 主键, head_commit CHAR(40), synced_rev BIGINT, updated_at）

### Git 同步（规划中）

目标：用户可以 `git clone` 自己的笔记到本地，用任意编辑器修改后 `git push` 回网页，网页上的修改也能 `git pull` 到本地。
价值：本地 / 离线编辑、数据完全归用户所有、通过提交记录得到历史版本。

#### 分阶段

| 阶段 | 内容 |
|---|---|
| 第一版 | 不实现 Git，但数据模型先满足下方「兼容约束」，避免以后做数据迁移 |
| 第二版 | 只读 Git：支持 `clone` / `pull`，不存在冲突问题 |
| 第三版 | 双向同步：支持 `push`，处理重命名、冲突和推送校验 |

#### 兼容约束（第一版就要满足）
- **同一文件夹下笔记标题唯一、子文件夹名唯一**，数据库加唯一约束，前端新建 / 重命名 / 移动时校验
- 标题和文件夹名不能包含文件名非法字符（`/ \ : * ? " < > |`），不能是 `.` 或 `..`
- 笔记的 `id`、`public_id` 与标题、路径无关，改名或移动不改变它们，保证分享链接永久有效
- 正文以纯 Markdown 文本存储，不在正文中混入平台私有的元数据

#### 映射规则
- 每个用户一个仓库，文件夹对应目录，笔记对应 `标题.md`，正文即文件内容
- 仓库中只有用户自己的目录和 `.md` 文件，不放任何平台私有文件，也不使用 front matter 记录 id
- 「文件路径 → 笔记 id」直接从数据库推导：推送前数据库内容一定与用户推送所基于的提交完全一致（见下方 push 流程），所以旧路径对应哪篇笔记查数据库即可

#### 实现方案
- **以数据库为准，Git 仓库只是镜像**，网页端的现有设计不需要改动
- 服务端为每个用户维护一个裸仓库（如 `/data/git/{user_id}.git`，挂载为持久化目录），用 dulwich 实现 Git Smart HTTP 协议，认证用 HTTP Basic（密码为访问令牌）
- **fetch / pull**：对该用户加锁，比较 `user.content_rev` 与 `git_repo.synced_rev`，不相等说明网页上有修改，从数据库生成目录树并提交一个快照，更新 `synced_rev`。网页每秒的自动保存不会各自生成提交
- **push**：
  - 先按 fetch 的逻辑检查，网页端有新修改就先生成快照，此时用户的推送不是快进，Git 客户端会提示先 `pull` 合并，与普通 Git 协作一致
  - 只接受快进推送，解析新旧提交的差异（带重命名检测），在一个数据库事务中写回：新增、修改、删除、改名 / 移动（笔记 id 不变，分享链接继续有效）
  - 写回后更新 `git_repo.head_commit` 和 `synced_rev`
  - 写回时笔记 `version` 加 1。如果该笔记正在浏览器中编辑，浏览器下次保存会收到 409，复用现有的冲突处理弹窗
- **推送校验**：只接受 `.md` 文件和目录，拒绝其他文件类型、超大文件、非法文件名和重名，并返回明确的错误信息

#### 认证
- 新增**个人访问令牌**：在网页设置中生成，`git clone` 时作为密码使用（不直接使用登录密码，泄露后可单独吊销）
- 令牌只存哈希，可以设置有效期、随时吊销

#### 待确认
- 第二版和第三版是否合并为一次开发
- 网页端是否展示 Git 提交历史（可以替代「历史版本快照」功能）

## 目录结构

```
underleaf/
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── deps.py             # 依赖注入（current_user 等）
│   │   ├── core/               # config、security、db session
│   │   ├── api/v1/             # 路由：auth、folders、notes、share、export
│   │   ├── models/             # SQLAlchemy 模型
│   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   └── services/           # 业务逻辑：导出、邮件发送等
│   ├── migrations/             # Alembic
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/                # 请求封装，按资源拆分
│       │   └── mock/           # 演示模式下的浏览器内 mock 后端
│       ├── components/
│       │   └── editor/         # 编辑器、预览、分栏、同步滚动
│       ├── composables/        # useAutoSave、useScrollSync 等
│       ├── markdown/           # markdown-it 实例与插件，唯一配置入口
│       ├── stores/             # Pinia
│       ├── views/              # 页面（PrintView 为 PDF 打印页）
│       └── router/
├── docker-compose.yml
└── README.md
```

## 开发规范

### API
- 统一使用 `/api/v1` 前缀，RESTful 风格
- 错误响应统一为 `{ "code": ..., "message": ..., "detail": ... }`
- JSON 字段使用 camelCase：后端通过 Pydantic 的 `alias_generator` 转换，Python 代码内部仍用 snake_case

### 后端分层
- 路由层（`api/`）只做参数校验和调用 service，不写业务逻辑
- 业务逻辑放在 `services/`
- 数据库访问统一使用 async session
- 配置通过 pydantic-settings 读取 `.env`；`.env.example` 提交到仓库，`.env` 不提交

### 数据库（MySQL）
- 字符集统一使用 `utf8mb4` + `utf8mb4_0900_ai_ci`，否则 emoji 等 4 字节字符无法存储
- 笔记正文使用 `MEDIUMTEXT`（上限 16MB），不要用 `TEXT`（上限只有 64KB）
- MySQL 的 DDL 会隐式提交，Alembic 迁移失败时不会自动回滚。每个迁移脚本只做一件事，上线前先在测试库上跑一遍

### 代码风格
- 后端：ruff（lint + format）+ pyright
- 前端：ESLint + Prettier
- 通过 pre-commit 统一执行

### Git
- 提交信息遵循 Conventional Commits：`feat:`、`fix:`、`refactor:`、`docs:`、`chore:` 等

## 本地开发

### 前端

```bash
cd frontend
pnpm install
pnpm dev          # http://localhost:5173
pnpm type-check   # 类型检查
pnpm lint         # ESLint
pnpm build        # 生产构建
```

- `.env.development` 中 `VITE_USE_MOCK=true` 时为**演示模式**：不需要后端，接口由 `src/api/mock/` 在浏览器内模拟，数据存在 localStorage
  - 验证码固定为 `123456`；演示账号 `demo@underleaf.dev` / `underleaf123`
  - 同一浏览器多个标签页共享数据，可以用来测试版本冲突
- 接入后端时把 `VITE_USE_MOCK` 改为 `false`，开发服务器会把 `/api` 代理到 `http://localhost:8000`
- 注意：TypeScript 固定在 5.9，vue-tsc 暂不兼容 TypeScript 7

### 后端

需要 Python 3.12、PDM、MySQL 8、Redis。

```bash
cd backend
pdm install
cp .env.example .env    # 填写 DATABASE_URL、REDIS_URL
pdm migrate             # 即 alembic upgrade head，建表 / 升级表结构
pdm dev                 # http://localhost:8000，接口文档 /api/docs
pdm lint                # ruff + pyright
TEST_DATABASE_URL=mysql+aiomysql://用户:密码@主机:3306/underleaf_test pdm test
```

- 库需要使用 `utf8mb4` + `utf8mb4_0900_ai_ci`，可以用 `SHOW CREATE DATABASE underleaf;` 确认
- **修改表结构的流程**：改 `app/models/` 中的模型 → `pdm run alembic revision --autogenerate -m "说明"` 生成迁移脚本 → 检查脚本内容（自动生成并不总是完全正确）→ 提交 → 在服务器上 `pdm migrate`
- 不要用 `Base.metadata.create_all()` 建正式库的表，它不会记录版本，后续无法升级
- 测试会清空 `TEST_DATABASE_URL` 指向的库，务必使用单独的测试库

### 接口约定（前端已按此实现，后端照此开发）

所有接口前缀 `/api/v1`，登录态通过 httpOnly Cookie 传递。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/auth/me` | 当前用户 `{ id, email, nickname }`，未登录返回 401 |
| PATCH | `/auth/me` | 修改昵称 `{ nickname }`，已被占用返回 409 |
| POST | `/auth/email-code` | 发送验证码 `{ email, purpose: "register" \| "login" \| "reset_password" }` |
| POST | `/auth/register` | 注册 `{ email, code, nickname, password }`，邮箱或昵称已被占用返回 409 |
| POST | `/auth/login/email-code` | 验证码登录 `{ email, code }`，未注册返回 404 |
| POST | `/auth/login/password` | 密码登录 `{ account, password }`，`account` 为邮箱或昵称 |
| POST | `/auth/password/reset` | 重置密码 `{ email, code, newPassword }` |
| PUT | `/auth/password` | 修改密码 `{ oldPassword, newPassword }` |
| POST | `/auth/logout` | 退出登录 |
| GET | `/folders` | 文件夹列表（扁平，前端组装成树） |
| POST | `/folders` | 新建 `{ name, parentId }` |
| PATCH | `/folders/{id}` | 重命名 / 移动 `{ name?, parentId? }` |
| DELETE | `/folders/{id}` | 级联删除子文件夹和笔记 |
| GET | `/notes` | 笔记元信息列表（不含正文） |
| POST | `/notes` | 新建 `{ title, folderId }` |
| GET | `/notes/{id}` | 笔记详情（含正文和 `version`） |
| PATCH | `/notes/{id}` | 修改标题 / 移动 / 公开开关 `{ title?, folderId?, isPublic? }` |
| PUT | `/notes/{id}/content` | 保存正文 `{ content, version }`，版本不一致返回 **409** |
| DELETE | `/notes/{id}` | 删除笔记 |
| GET | `/notes/{id}/export.pdf` | 导出 PDF，返回文件附件（后端 Chromium 生成） |
| GET | `/share/{publicId}` | 公开分享（无需登录）`{ title, content, updatedAt }`，未公开返回 404 |

前端会用到的错误码：401 未登录、404 不存在、409 版本冲突 / 邮箱或昵称已被占用、429 发送太频繁。
