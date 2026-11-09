# Git 同步的认证方式：访问令牌 vs SSH 公钥

Git 同步（readme「Git 同步」）需要确认「这次 clone / push 的是哪个用户」。讨论过两种做法，**最终采用访问令牌**，SSH 公钥暂不实现。本文记录对比和理由，以后需要时可以在此基础上再加 SSH。

## 两种方式的用法

### 访问令牌（已实现）

1. 网页「用户菜单 → Git 同步」中生成令牌（`ulp_` 开头），默认永不过期，之后随时可以在同一处查看和复制
2. `git clone http://网站/api/v1/git/{用户 id}/notes.git`
3. Git 提示输入时：用户名随意填写，密码粘贴令牌。只需输入一次，Git 会存进系统的凭据管理（macOS 钥匙串、Windows 凭据管理器），之后 pull / push 不再询问

### SSH 公钥（未实现）

1. 用户在本机生成密钥（已有的可以直接用，如 `~/.ssh/id_ed25519.pub`），把公钥内容粘贴到网页
2. `git clone git@网站:notes.git`，不需要输入任何东西

## 对比

| | 访问令牌 | SSH 公钥 |
|---|---|---|
| 首次设置 | 复制令牌，第一次 clone 时粘贴一次 | 粘贴公钥；没有密钥的用户要先学会生成 |
| 之后使用 | 不用再输入（Git 自动记住） | 不用输入 |
| 适合的用户 | 所有人，包括不熟悉命令行的用户 | 熟悉 Git / SSH 的开发者；Windows 和非技术用户门槛较高 |
| 传输安全 | 依赖 HTTPS。网站目前是 http，令牌以明文传输 | SSH 自带加密，不依赖 HTTPS |
| 泄露风险 | 令牌被截获即可使用，可单独吊销 | 私钥不离开用户电脑，服务器只存公钥 |
| 服务器改动 | 无：复用现有 Nginx 和后端，Nginx 加一段 `/api/v1/git/` 配置 | 大：新建 `git` 系统用户、修改 sshd 配置（改错可能导致管理员也无法 SSH 登录），或在后端内置 SSH 服务并在防火墙中放行新端口 |
| 是否可以单独存在 | 可以 | 不建议：不会用 SSH 的用户将无法同步，所以只能作为令牌之外的可选方式 |

## 代码量

快照、推送校验、写回数据库等核心逻辑（`app/services/git_repo.py`、`git_sync.py`，约 600 行）两种方式共用，下表只比较各自独有的部分。令牌一栏为已实现的实际行数，SSH 一栏为估算。

| 部分 | 访问令牌（已实现） | SSH 公钥（估算） |
|---|---|---|
| 凭据表 + 迁移 | `access_token`，约 30 行 | `ssh_key`，约 30 行 |
| 管理接口 | 生成 / 列表 / 吊销，约 90 行 | 添加 / 列表 / 删除，外加公钥格式校验、计算指纹、防止同一公钥绑定多个账号，约 130 行 |
| 认证 | 解析 HTTP Basic、比对哈希，约 70 行 | `AuthorizedKeysCommand` 查询程序 + 强制命令入口（解析 `SSH_ORIGINAL_COMMAND`、校验仓库路径、把标准输入输出交给 dulwich），约 120 行 |
| 协议层 | Smart HTTP 路由 + 无状态处理，约 280 行 | 不需要 HTTP 路由，处理有状态的 SSH 协议，约 60 行 |
| 前端 | 弹窗，约 250 行 | 弹窗（粘贴公钥），约 250 行 |
| 服务器配置 | Nginx 加一段 location | `git` 系统用户、sshd 配置、权限，以及部署脚本和文档 |

单看各自的代码，两者差不多，SSH 略多。但令牌方式已经完成；SSH 只能在令牌之外**额外**增加，等于再写约 500 行，主要风险在服务器配置而不在代码。

## 结论

- 采用访问令牌：已实现、所有用户都能用、服务器几乎不用改
- 为了减少麻烦：令牌默认**永不过期**，并且用户**随时可以在网页上查看和复制**（不再是「只显示一次」）
- 当前最大的短板是网站没有 HTTPS，令牌（以及登录密码）以明文传输。**应尽早开启 HTTPS**，这比增加 SSH 更重要

## 令牌的存储方式

为了让用户随时能查看，服务器必须能还原令牌，不能只存哈希：

- `token_hash`：SHA-256，用于校验和查找（唯一索引）
- `token_encrypted`：Fernet 加密的令牌，只用于网页显示。密钥由 `JWT_SECRET` 经 HKDF 派生，数据库单独泄露时拿不到可用的令牌
- 更换 `JWT_SECRET` 后旧令牌**照常可用**，只是网页上无法再显示（提示重新生成）
- 实现位置：`backend/app/services/access_tokens.py`

## 以后如果要加 SSH

推荐复用系统 sshd，地址简洁，也不用开新端口：

1. 新建 `ssh_key` 表（id, user_id, name, public_key, fingerprint 唯一, last_used_at, created_at）和网页上的管理界面
2. 服务器新建 `git` 系统用户（无密码、不能登录 shell）
3. sshd 配置 `Match User git`：`AuthorizedKeysCommand` 指向一个按指纹查询数据库的程序，返回 `command="…入口程序 <key_id>",no-pty,no-port-forwarding,no-X11-forwarding,no-agent-forwarding <公钥>`
4. 入口程序根据 `SSH_ORIGINAL_COMMAND`（`git-upload-pack` / `git-receive-pack`）调用 dulwich 的处理器（`stateless_rpc=False`，直接读写标准输入输出），复用 `git_sync.sync_snapshot` / `apply_push`
5. 修改 sshd 前备份配置、用 `sshd -t` 检查，并保持一个已登录的 SSH 会话，防止把自己锁在外面
