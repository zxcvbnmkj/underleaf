# 在线 MarkDown 的知识管理平台
## 来源
- 借鉴了 overleaf 这种在线的 latex 编辑器，左侧编辑右侧渲染
- 线上托管笔记，避免跨设备进度不同步，需要传来出去的问题，也不怕丢失，便于管理

## 功能
- 笔记按**文件夹树**组织
- 左侧编辑、右侧实时预览，支持同步滚动
- 图片：在编辑器中粘贴或拖入图片即自动上传并插入链接，存在服务器本机，详见 [docs/images.md](docs/images.md)
- 目录：列出 1～3 级标题，点击跳转，滚动时高亮当前章节
  - 编辑页：编辑区和预览区一起滚动；宽屏为右侧面板（可隐藏），窄屏为抽屉
  - 分享页：宽屏固定在正文右侧，窄屏通过右下角「目录」按钮打开；没有标题时不显示
- 笔记支持网页链接分享（**只读**）、下载为 PDF、下载为 Word
- 自动保存（停止输入 30 秒等时机）+ 本地草稿防丢失；多设备编辑同一篇时检测冲突，不静默覆盖
- 注册填写邮箱 + 昵称 + 密码（不需要验证码）；登录支持「邮箱 / 昵称 + 密码」和「邮箱 + 验证码」；忘记密码可以用验证码登录或重置密码
- 通过 Git 在本地与网页之间同步笔记（clone / pull / push），访问令牌在「用户菜单 → Git 同步」中生成，详见「Git 同步」

### 暂不考虑
- 微信登录
- 历史版本快照
- 多人实时协同编辑

## 技术选型

| 层 | 选型 | 说明 |
|---|---|---|
| 后端框架 | FastAPI + Pydantic v2 | |
| ORM / 迁移 | SQLAlchemy 2.0（async）+ Alembic | |
| 数据库 | MySQL 5.7（驱动 aiomysql） | 复用服务器已有实例（5.7.44，库名 `underleaf`）；不使用 8.0 才有的特性（递归 CTE、窗口函数等），以后升级到 8 无需改代码 |
| 缓存 | Redis（redis-py asyncio） | 存验证码、发送冷却等短期数据，靠 TTL 自动过期 |
| 认证 | 邮箱验证码 / 账号密码 + JWT（httpOnly Cookie） | 密码用 Argon2 哈希（pwdlib）；邮件通过 SMTP 发送（aiosmtplib） |
| 导出 | Playwright（PDF）、Pandoc（Word，pypandoc-binary 自带） | PDF 由后端无头 Chromium 打印前端渲染页；Word 由 Pandoc 转换，Mermaid 图表由 Chromium 截图插入 |
| 后端工具 | PDM + ruff + pyright + pytest | |
| 前端 | Vue3 + Vite + TypeScript + Pinia + Vue Router | |
| 编辑器 | CodeMirror 6 | 比 Monaco 轻，移动端友好 |
| 渲染 | markdown-it + KaTeX + Shiki + Mermaid | |
| UI 库 | Naive UI | 对 TS 友好 |
| 部署 | 云效 Flow 流水线 + 主机部署（不使用 Docker）+ Nginx | 详见 [docs/pipeline.md](docs/pipeline.md) |

## 关键设计

### 渲染一致性
- **预览与 PDF 同源**：PDF 由前端渲染页 `/export/render` 打印而来，该页和编辑区预览、分享页使用同一个 `MarkdownPreview` 组件和 `markdown.css`，优化渲染效果后 PDF 自动跟着变，无需单独修改
- **Word 走 Pandoc**：公式转为 Word 原生公式；Mermaid 图表由 Chromium 按预览截图后插入，见「Word 导出」
- **语法范围收窄**：只支持 GFM + KaTeX 公式 + 代码高亮 + Mermaid。markdown-it 插件统一放在 `frontend/src/markdown/` 中配置，新增语法前要确认 Pandoc 也能正确导出

### PDF 导出

用户点击「导出 → 导出 PDF」直接下载文件，不弹打印对话框、不带页眉页脚。PDF 在服务器上由无头 Chromium 生成，和用户用什么浏览器无关。

#### 流程
1. 前端把**编辑器中当前的**标题和正文 `POST /api/v1/export/pdf`（不需要先保存）
2. 后端用 Playwright 控制无头 Chromium，在页面加载前注入 `window.__UNDERLEAF_EXPORT__ = { title, content }`，然后打开前端渲染页 `/export/render`
3. 渲染页用 `MarkdownPreview` 渲染，全部完成后在 `<html>` 上设置 `data-export-ready="true"`（没有注入内容时为 `"error"`）
4. 后端等到该标记后调用 `page.pdf({ preferCSSPageSize: true, printBackground: true })`，纸张和页边距由 `markdown.css` 的 `@page` 决定
5. 以附件形式返回，前端拿到文件后触发下载

为什么由前端传内容，而不是后端按笔记 id 读取：渲染页不需要登录、后端不用转发登录 Cookie；导出的是编辑器中的最新内容。

#### 渲染页（`frontend/src/views/ExportRenderView.vue`）
- 固定浅色主题；屏幕上按 A4 版心宽度显示，便于直接打开调试
- 正文不以一级标题开头时补上标题；`<title>` 设为笔记标题
- 等字体、图片、Mermaid 全部渲染完成后才设置就绪标记，避免打出半成品
- 不需要登录，不读取任何接口，没有注入内容时只显示一段说明

#### 打印样式
集中在 `markdown.css` 的 `@page` 和 `@media print` 中：代码自动换行而非横向滚动、表格铺满、过宽的图表缩放、标题不落在页尾、代码块 / 公式 / 图表 / 表格行尽量不被分页切开。

**改渲染时需要注意**：普通样式调整不用管导出；只有以下情况要同步处理——
- 新增可能比纸宽或不宜被切开的块 → 在 `@media print` 中补规则
- 新增异步渲染步骤（类似 Mermaid）→ 必须在 `MarkdownPreview` 触发 `rendered` 之前完成，否则打印时还没画出来
- 新增颜色 → 浅色主题下也要清晰（打印固定浅色）
- 新增语法 → 还要确认 Pandoc 能导出 Word（Word 不复用前端渲染）

#### 后端实现（`backend/app/services/pdf.py`）
- **只用 Chromium**：Playwright 支持三种内核，但只有 Chromium 能生成 PDF
- **复用浏览器**：首次导出时启动 Chromium 并常驻（不导出就不占内存），每次导出新建一个浏览器上下文、用完关闭；Chromium 意外退出时自动重启。实测首次导出约 3～4 秒，之后约 1.5 秒
- **限流**：信号量限制同时导出的数量（`EXPORT_CONCURRENCY`，默认 2），超出的排队；单次导出 30 秒超时（含排队）；正文上限 5MB
- **文件名**：去掉文件名非法字符，响应头 `Content-Disposition: attachment; filename*=UTF-8''<URL 编码后的标题>.pdf`，保证中文文件名在各浏览器都正常
- **配置项**：`EXPORT_RENDER_URL`（Chromium 访问前端的地址：本地为 `http://localhost:5173`，服务器为本机 Nginx `http://127.0.0.1:10002`）；`EXPORT_BROWSER_CHANNEL`（本地填 `chrome` 可直接使用已安装的 Google Chrome，服务器留空使用 Playwright 自带的 Chromium）
- **待办**：登录功能完成后，接口加上登录校验，并按用户限制导出频率

#### 部署
- 服务器上一次性安装 Chromium 及其系统依赖、中文和 emoji 字体（否则 PDF 中的中文显示为方块），命令见 [docs/pipeline.md](docs/pipeline.md)「导出 PDF 所需依赖」
- Nginx 的 `/api/` 需要设置 `client_max_body_size 11m`（默认 1MB，长笔记导出、上传图片会被拒绝）
- 资源占用：常驻的 Chromium 约一两百 MB 内存；服务器只有 2GB 内存，并发数不宜调高

### Word 导出

与 PDF 相同：前端把编辑器中当前的标题和正文 `POST /api/v1/export/docx`，后端生成后直接下载。

- **转换工具**：Pandoc，通过 `pypandoc-binary` 安装（Python 包自带 Pandoc 程序，服务器无需另外安装）
- **输入格式**：`gfm+tex_math_dollars`，与前端 markdown-it 对齐（GFM 表格、任务列表、删除线，`$` / `$$` 公式）
- **公式**：转为 Word 原生公式，可以在 Word 中继续编辑
- **代码块**：保留语法高亮
- **Mermaid 图表**：Pandoc 不能画图。正文包含 Mermaid 时，后端用 Chromium 打开导出渲染页（与 PDF 共用），按文档顺序对每个图表截图（2 倍分辨率），由 Lua 过滤器替换对应的代码块。渲染失败的图表保留为代码块；截图数量与代码块数量对不上时全部保留为代码块，避免错位。不包含 Mermaid 时不启动 Chromium
- **原始 HTML**：网页预览禁用了 HTML（按文字显示），Word 中同样按文字输出；Pandoc 默认会直接丢弃
- **标题**：正文不以一级标题开头时，用笔记标题作为文档标题（与网页一致）
- **图片**：站内图片从磁盘读取，公网图片全部下载后插入；不下载解析到内网 / 本机地址的图片，不读取上传目录以外的服务器文件（见 `backend/app/services/export_images.py`）
- **安全**：Pandoc 以 `--sandbox` 运行，自身不读取本地文件、不访问网络，图片都由后端预先取好再交给它
- **样式**：使用 Pandoc 默认模板（新版 Office 默认样式，中文为等线）。以后需要统一字体、标题颜色时，可以提供自定义的 `reference.docx`
- **实现位置**：`backend/app/services/docx.py`（调用 Pandoc）、`backend/app/services/pandoc/underleaf.lua`（Lua 过滤器）、`backend/app/services/browser.py`（Chromium，PDF 与图表截图共用）

### 多设备防覆盖
- 笔记带 `version` 字段，保存时校验版本（乐观锁）：`UPDATE ... SET version = version + 1 WHERE id = ? AND version = ?`，影响行数为 0 即冲突，提示用户而不直接覆盖

### 保存策略
目标：减少对服务器的保存次数，同时不丢内容。逻辑在 `frontend/src/composables/useNoteEditor.ts`。

- **自动保存到服务器的时机**：
  - 停止输入 30 秒后
  - 持续输入满 2 分钟（即使没有停顿，避免长时间写作一直不同步）
  - 编辑器失去焦点、页面切到后台（切换标签页、最小化、手机切到后台）、切换笔记时立即保存
  - 手动：`Ctrl/⌘ + S`，或点击工具栏中的「未保存」
- **同一时间只有一个保存请求**，保存期间的新输入在完成后继续保存；网络错误时 5 秒后自动重试
- **离开提醒**：关闭或刷新页面时有未保存的内容，浏览器弹出确认
- **本地草稿**（`frontend/src/composables/noteDrafts.ts`）：防止停电、浏览器崩溃等来不及保存的情况
  - 输入后 0.5 秒把正文写入 localStorage（键为 `underleaf-draft:{userId}:{noteId}`），不访问服务器；保存成功后删除
  - 打开笔记时发现草稿：服务器版本与草稿所基于的版本相同 → 自动恢复并提示；服务器在此之后被修改过（如其他设备）→ 弹窗让用户选择恢复或丢弃
  - 草稿只在当前浏览器中，保存或丢弃前一直保留；localStorage 不可用或超出容量（约 5MB）时不影响编辑，只是没有草稿保护

### 文件夹树
- `folder` 表通过 `parent_id` 自关联形成树，笔记通过 `folder_id` 归属到文件夹
- 树的层级不深，整棵树一次性下发，由前端组装

### 只读分享
- 笔记带 `is_public` 开关，打开后可以通过 `/s/{public_id}` 公开访问只读渲染页，链接永久有效
- `public_id` 是建笔记时生成的随机字符串（如 nanoid），不能用自增 id，否则别人可以通过遍历 id 访问所有公开笔记
- 关闭开关后链接立即失效，再次打开后恢复为原链接
- 分享页显示作者昵称（不显示邮箱）、创建时间和更新时间，以及目录

### 登录
- 一个邮箱对应一个用户；昵称也全局唯一（不区分大小写）
- **注册**：填写邮箱、昵称、密码 → 注册并登录（不校验邮箱，无需验证码）。邮箱或昵称已被占用时提示
- **登录（三种方式，登录的是同一个账号）**：
  - 邮箱 + 密码
  - 昵称 + 密码（与上一种共用一个输入框，后端根据是否包含 `@` 区分，因此昵称不能包含 `@`）
  - 邮箱 + 验证码（邮箱未注册时提示先注册，不自动注册）
- **忘记密码**：用验证码登录，或通过邮箱验证码重置密码
- **昵称规则**：2～20 个字符，允许中文、字母、数字、`_`、`-`，不能包含 `@` 和空格；注册后可以修改
- **密码**：Argon2 哈希存储，至少 8 位；登录失败统一提示「账号或密码错误」
- **不做账号锁定**：防暴力破解靠按 IP 限流（Redis 计数）：登录接口每分钟 10 次，发验证码每分钟 5 次；账号不存在时也做一次同样耗时的密码校验，无法通过响应时间判断账号是否存在
- **验证码**：存 Redis（只存哈希），不建表
  - 有效期 5 分钟（Redis TTL 自动过期），同一邮箱 60 秒内只能发送一次，连续输错 5 次作废，验证成功后立即删除
  - 区分用途：登录 / 重置密码，不能混用
  - 不能放在后端进程内存中：重启会丢失，多 worker 部署时发码和验码可能落在不同进程
- **登录态**：JWT（HS256，有效期 30 天）放在 httpOnly、SameSite=Lax 的 Cookie `underleaf_session` 中，前端 JS 读不到。JWT 中带 `token_version`：
  - 修改密码：版本加 1，其他设备失效，当前设备换发新令牌保持登录
  - 重置密码：版本加 1，所有设备失效，需要用新密码重新登录
  - 退出登录：只清除当前设备的 Cookie
- **邮件**：SMTP 发送（aiosmtplib），配置见 `backend/.env.example`。未配置时，开发环境把验证码打印到后端日志，正式环境拒绝发送
- **需要登录的接口**：除注册、登录、发验证码、重置密码、公开分享外都需要登录；导出每人每分钟 20 次，上传图片每人每分钟 60 次
- **实现位置**：`backend/app/api/v1/auth.py`（接口）、`app/services/email_codes.py`（验证码）、`app/core/security.py`（密码哈希与 JWT）、`app/api/deps.py`（当前用户）

### 数据库表
- 统一约定：主键 `BIGINT` 自增；时间用 `DATETIME(3)` 存 UTC；字符集 `utf8mb4` + `utf8mb4_unicode_520_ci`（比较名字时不区分大小写和重音，与 Windows / macOS 文件系统一致，利于 Git 同步；不用 `unicode_ci` / `general_ci`，它们把所有 emoji 视为同一个字符）
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
- **`image`**（图片）：id, user_id（可空，删除用户时置空）, path（相对上传目录，唯一）, mime, size, created_at / updated_at。文件本身存在磁盘上，见 [docs/images.md](docs/images.md)
- **`access_token`**（Git 访问令牌）：id, user_id（级联删除）, name, token_hash（SHA-256，唯一，用于校验）, token_encrypted（加密的令牌，供网页查看）, last_chars（末尾 4 个字符，用于辨认）, expires_at / last_used_at / revoked_at（可空）, created_at / updated_at
- **`git_repo`**（每个用户的仓库状态，同时作为该用户 Git 操作的行锁）：user_id 主键（级联删除）, head_commit, synced_rev（可空，生成快照时的 `user.content_rev`）, updated_at

### Git 同步

目标：用户可以 `git clone` 自己的笔记到本地，用任意编辑器修改后 `git push` 回网页，网页上的修改也能 `git pull` 到本地。
价值：本地 / 离线编辑、数据完全归用户所有、通过提交记录得到历史版本。

#### 分阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| 第一版 | 不实现 Git，但数据模型先满足下方「兼容约束」，避免以后做数据迁移 | 已完成 |
| 第二版 | 只读 Git：支持 `clone` / `pull`，不存在冲突问题 | 已完成 |
| 第三版 | 双向同步：支持 `push`，处理重命名、冲突和推送校验 | 已完成 |

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
- 仓库地址：`{网站}/api/v1/git/{user_id}/notes.git`，只有一个分支 `main`
- 服务端为每个用户维护一个裸仓库 `{GIT_REPO_DIR}/{user_id}.git`（服务器上在 `/home/ubuntu/data/underleaf/git`），用 dulwich 实现 Git Smart HTTP 协议，认证用 HTTP Basic（用户名随意，密码为访问令牌）
- 加锁：`git_repo` 行 `SELECT ... FOR UPDATE`，同一用户的快照和推送串行执行
- **fetch / pull**：对该用户加锁，比较 `user.content_rev` 与 `git_repo.synced_rev`，不相等说明网页上有修改，从数据库生成目录树并提交一个快照，更新 `synced_rev`。网页上的多次自动保存不会各自生成提交
- **push**：
  - 先按 fetch 的逻辑检查，网页端有新修改就先生成快照，此时用户的推送不是快进，Git 客户端会提示先 `pull` 合并，与普通 Git 协作一致
  - 只接受快进推送，解析新旧提交的差异（带重命名检测），在一个数据库事务中写回：新增、修改、删除、改名 / 移动（笔记 id 不变，分享链接继续有效）
  - 写回顺序：删除笔记 → 要移动的笔记先移到根目录并改为临时标题 → 删除目录消失的文件夹 → 新建文件夹 → 笔记移到最终位置、更新正文、新建笔记（避免中途撞唯一索引）
  - 文件夹按路径（不区分大小写）对应；仓库中看不到的空文件夹保留，旧提交中有、新提交中消失的目录删除
  - 改名检测与 git 一致：内容相似度 ≥ 60%（按行比较）视为同一篇；名字互换在 git 看来是两篇各自修改，笔记 id 跟随路径
  - 写回后更新 `git_repo.head_commit` 和 `synced_rev`；先更新 main 再提交事务，提交失败时把 main 改回去
  - 正文有变化的笔记 `version` 加 1（只改名 / 移动时不变，与网页端一致）。如果该笔记正在浏览器中编辑，浏览器下次保存会收到 409，复用现有的冲突处理弹窗
- **推送校验**：只接受 `.md` 文件和目录，拒绝其他文件类型、符号链接、子模块、超大文件（5MB）、非 UTF-8 内容、非法文件名（含首尾空白）、超过 10 层的目录和重名（不区分大小写），并逐条返回错误信息（显示为 `remote: ...`）；只能推送 `main`，不能删除分支
- **实现位置**：`app/api/v1/git.py`（Smart HTTP 接口）、`app/api/v1/tokens.py`（令牌管理）、`app/services/git_repo.py`（快照、推送校验与写回计划，不访问数据库）、`app/services/git_sync.py`（加锁、快照、写回数据库）、`app/services/git_http.py`（dulwich 协议处理）

#### 认证
- 使用**个人访问令牌**（不做 SSH 公钥，对比和理由见 [docs/git-auth.md](docs/git-auth.md)）：在网页「用户菜单 → Git 同步」中生成，`git clone` 时作为密码使用，只需输入一次，Git 会自动记住（不直接使用登录密码，泄露后可单独吊销）
- 令牌格式 `ulp_` + 43 个随机字符，默认永不过期（也可以选 30 天 / 90 天 / 1 年），随时可以在网页上查看和复制、随时吊销；每个用户最多 20 个有效令牌
- 存储：校验用 SHA-256 哈希；另存一份加密的令牌供查看，密钥由 `JWT_SECRET` 派生。更换 `JWT_SECRET` 后令牌照常可用，只是网页上无法再显示
- 认证失败按 IP 限流（10 分钟 20 次），push 按用户限流（每分钟 30 次）

#### 已知限制
- 空文件夹无法出现在仓库中（Git 不记录空目录）
- 服务器上的仓库目录丢失后会从数据库重新生成，历史与本地不连续，本地需要重新 clone
- 网页端打开着的文件夹树不会自动刷新，push 后刷新网页即可看到

#### 待确认
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
│   │   ├── api/v1/             # 路由：auth、folders、notes、share、export、images、tokens、git
│   │   ├── models/             # SQLAlchemy 模型
│   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   └── services/           # 业务逻辑：导出、邮件发送等
│   ├── migrations/             # Alembic
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/                # 请求封装，按资源拆分
│       ├── components/
│       │   └── editor/         # 编辑器、预览、分栏、同步滚动
│       ├── composables/        # useAutoSave、useScrollSync 等
│       ├── markdown/           # markdown-it 实例与插件，唯一配置入口
│       ├── stores/             # Pinia
│       ├── views/              # 页面（ExportRenderView 为 PDF 导出渲染页）
│       └── router/
├── docs/                   # 专题文档：pipeline.md（部署流水线）、images.md（图片存储与迁移）、git-auth.md（Git 认证方式对比）
├── restart.sh              # 服务器上的后端进程管理（start / stop / restart / status / logs）
└── readme.md
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
- 字符集统一使用 `utf8mb4`（否则 emoji 等 4 字节字符无法存储），排序规则 `utf8mb4_unicode_520_ci`
- 服务器是 MySQL 5.7：不要使用 8.0 才有的语法（`WITH RECURSIVE`、窗口函数、`utf8mb4_0900_*` 排序规则、TEXT 列的表达式默认值等）
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

- 前端依赖后端：先启动后端（见下方「后端」），开发服务器会把 `/api`、`/uploads` 代理到 `http://localhost:8000`
- 本地未配置 SMTP 时，登录 / 重置密码的验证码打印在后端日志中
- 注意：TypeScript 固定在 5.9，vue-tsc 暂不兼容 TypeScript 7

### 后端

需要 Python 3.12、PDM、MySQL 5.7 或 8、Redis。

```bash
cd backend
pdm install
cp .env.example .env    # 填写 DATABASE_URL、REDIS_URL
pdm migrate             # 即 alembic upgrade head，建表 / 升级表结构
pdm dev                 # http://localhost:8000，接口文档 /api/docs
pdm lint                # ruff + pyright
TEST_DATABASE_URL=mysql+aiomysql://用户:密码@主机:3306/underleaf_test pdm test
```

- 库需要使用 `utf8mb4`，可以用 `SHOW CREATE DATABASE underleaf;` 确认
- **连接服务器上的 MySQL 和 Redis**（本机不安装）：先执行 `pdm tunnel`（即 `bash scripts/tunnel.sh`），通过 SSH 隧道把服务器的 3306、6379 转发到本机，`.env` 中用 `127.0.0.1` 访问；`bash scripts/tunnel.sh stop` 关闭。需要能免密 `ssh ubuntu@124.223.10.25`
  - 数据库直接使用**线上 `underleaf` 库**：本地注册的账号和笔记会出现在线上；本地 `pdm migrate` 会提前修改线上表结构，迁移只做向后兼容的改动（新增表 / 带默认值的字段）
  - Redis 使用 **15 号库**（`REDIS_URL` 末尾的 `/15`），与线上的 0 号库隔开
  - 服务器上没有测试库，不要把 `TEST_DATABASE_URL` 指向 `underleaf`（测试会清空它）；需要跑数据库测试时另建 `underleaf_test`
- **修改表结构的流程**：改 `app/models/` 中的模型 → `pdm run alembic revision --autogenerate -m "说明"` 生成迁移脚本 → 检查脚本内容（自动生成并不总是完全正确）→ 提交 → 在服务器上 `pdm migrate`
- 不要用 `Base.metadata.create_all()` 建正式库的表，它不会记录版本，后续无法升级
- 测试会清空 `TEST_DATABASE_URL` 指向的库，务必使用单独的测试库

### 接口约定（前后端均已实现）

所有接口前缀 `/api/v1`，登录态通过 httpOnly Cookie 传递。时间字段均为 UTC 的 ISO 8601 格式并以 `Z` 结尾（如 `2026-11-08T13:49:02.123Z`），前端按本地时区显示。

- **名称规则**（文件夹名、笔记标题，为以后的 Git 同步预留）：去掉首尾空白后不能为空，UTF-8 不超过 240 字节（约 80 个汉字），不能包含 `/ \ : * ? " < > |`，不能是 `.` 或 `..`；同一位置不能重名（不区分大小写）
- **内容版本计数**：新建、重命名、移动、删除、保存正文时 `user.content_rev` 加 1（只切换公开分享不加），供 Git 同步判断是否需要生成快照
- **实现位置**：`backend/app/api/v1/folders.py`、`notes.py`（含公开分享），公共逻辑在 `app/services/notes.py`、`names.py`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/auth/me` | 当前用户 `{ id, email, nickname }`，未登录返回 401 |
| PATCH | `/auth/me` | 修改昵称 `{ nickname }`，已被占用返回 409 |
| POST | `/auth/email-code` | 发送验证码 `{ email, purpose: "login" \| "reset_password" }`，邮箱必须已注册 |
| POST | `/auth/register` | 注册 `{ email, nickname, password }`，邮箱或昵称已被占用返回 409 |
| POST | `/auth/login/email-code` | 验证码登录 `{ email, code }`，未注册返回 404 |
| POST | `/auth/login/password` | 密码登录 `{ account, password }`，`account` 为邮箱或昵称 |
| POST | `/auth/password/reset` | 重置密码 `{ email, code, newPassword }` |
| PUT | `/auth/password` | 修改密码 `{ oldPassword, newPassword }` |
| POST | `/auth/logout` | 退出登录 |
| GET | `/folders` | 文件夹列表（扁平，前端组装成树） |
| POST | `/folders` | 新建 `{ name, parentId }`；同一位置重名返回 409，超过 10 层返回 400 |
| PATCH | `/folders/{id}` | 重命名 / 移动 `{ name?, parentId? }`，`parentId: null` 表示移到根目录；不能移到自身或子文件夹下 |
| DELETE | `/folders/{id}` | 级联删除子文件夹和笔记 |
| GET | `/notes` | 笔记元信息列表（不含正文），每项 `{ id, title, folderId, isPublic, publicId, version, createdAt, updatedAt }` |
| GET | `/notes/recent?limit=8` | 最近编辑的笔记（按更新时间倒序，limit 1～20），每项为元信息加 `excerpt`：正文开头去掉 Markdown 标记后的纯文本，最多 120 字 |
| POST | `/notes` | 新建 `{ title?, folderId? }`，标题默认「未命名笔记」，同一文件夹下重名时自动编号（未命名笔记 2） |
| GET | `/notes/{id}` | 笔记详情（含正文和 `version`） |
| PATCH | `/notes/{id}` | 修改标题 / 移动 / 公开开关 `{ title?, folderId?, isPublic? }`，重名返回 409；不改变版本号 |
| PUT | `/notes/{id}/content` | 保存正文 `{ content, version }`，版本不一致返回 **409**，正文超过 5MB 返回 413 |
| DELETE | `/notes/{id}` | 删除笔记 |
| POST | `/export/pdf` | 导出 PDF `{ title, content }`，返回 PDF 文件附件；正文超过 5MB 返回 413，超时返回 504 |
| POST | `/export/docx` | 导出 Word `{ title, content }`，返回 docx 文件附件；错误码同上 |
| POST | `/images` | 上传图片，请求体为图片二进制（PNG / JPG / GIF / WebP，≤10MB），返回 `{ url, mime, size }`；`url` 为站内相对地址 `/uploads/...`。超限 413，格式不支持 415 |
| GET | `/share/{publicId}` | 公开分享（无需登录）`{ title, content, createdAt, updatedAt, author: { nickname } }`，未公开返回 404；作者只返回昵称，不返回邮箱 |

前端会用到的错误码：

| 状态码 | code | 含义 |
|---|---|---|
| 400 | `code_invalid` / `wrong_password` / `invalid_move` / `too_deep` | 验证码错误或过期 / 原密码不正确 / 不能移到自身或子文件夹下 / 文件夹超过 10 层 |
| 401 | `unauthorized` / `invalid_credentials` | 未登录或登录已失效 / 账号或密码错误 |
| 404 | `email_not_registered` / `not_found` | 邮箱未注册 / 资源不存在 |
| 409 | `email_registered` / `nickname_taken` / `name_taken` / `version_conflict` | 邮箱已注册 / 昵称已被使用 / 同一位置重名 / 笔记已在别处修改 |
| 413 / 415 | `content_too_large` / `image_too_large` / `image_unsupported` | 内容或图片过大 / 图片格式不支持 |
| 422 | `validation_error` / `invalid_name` | 参数校验失败 / 文件夹名或标题不合法；`message` 为可直接展示的中文提示 |
| 429 | `code_cooldown` / `too_many_requests` | 验证码发送太频繁 / 操作太频繁，`detail.retryAfter` 为需要等待的秒数 |
