# 部署流水线（云效 Flow）

记录 Underleaf 的自动化部署：服务器怎么准备、流水线怎么配置、出问题怎么回滚。
不使用 Docker，直接部署在服务器上；只有一个环境（正式环境）。

## 当前部署状态（2026-11-08）

| 项目 | 状态 |
|---|---|
| 访问地址 | `http://124.223.10.25:10002`（需要在腾讯云轻量服务器控制台的防火墙中放行 TCP 10002） |
| 前端 | 线上仍是旧版本（演示模式构建，数据只存在访问者浏览器中）。代码中的演示模式已删除，下次部署后即使用真实后端 |
| 后端 | 已启动，`127.0.0.1:8100`，经 Nginx 访问 `/api/v1/health` 正常；目前只有健康检查接口 |
| 数据库 | MySQL 5.7.44（宝塔安装），库 `underleaf` 已建表；程序使用账号 `underleaf_app`（只能从本机访问 `underleaf` 库，密码在 `shared/.env` 中） |
| Redis | 已安装并运行 |
| Nginx | 已配置（10002 端口） |
| PDF / Word 导出 | 代码已完成（PDF 由后端 Chromium 生成；Word 由 Pandoc 生成，`pypandoc-binary` 随依赖自动安装，图表截图也需要 Chromium），**服务器尚未配置**。下次部署前需要：安装 Chromium 和字体（「一、5」）、`shared/.env` 加 `EXPORT_RENDER_URL`（「一、3」）、Nginx 的 `/api/` 加 `client_max_body_size 11m`（「一、4」） |
| 图片上传 | 代码已完成，**服务器尚未配置**：创建 `shared/uploads`、`.env` 加 `UPLOAD_DIR`、Nginx 加 `/uploads/`，见 [images.md](images.md)「服务器配置」 |
| 登录 | 代码已完成，**服务器尚未配置**：`shared/.env` 必须加 `JWT_SECRET`（否则新版本后端无法启动）和 SMTP 邮箱配置（「一、3」） |
| Git 同步 | 代码已完成，**服务器尚未配置**：创建 `shared/git`、`.env` 加 `GIT_REPO_DIR`（「一、3」）、Nginx 加 `/api/v1/git/` 的 location（「一、4」）；数据库迁移随部署自动执行 |
| 流水线 | 未创建，目前为手动部署（见「六、手动部署」） |

## 总览

```
推送到 main
   ↓
阶段一「构建」（云效构建机）
   前端：pnpm install → ESLint → 类型检查 + 打包
   打包：deploy/package.sh 只收集服务器需要的文件 → 上传为制品
   ↓
阶段二「部署」（云效主机部署，登录服务器执行）
   deploy/deploy.sh：
   解压到新版本目录 → 链接共享配置 → 安装依赖 → 数据库迁移
   → 切换 current 软链接 → 重启后端 → 健康检查（失败自动回滚到上一版本）
```

| 组件 | 运行方式 |
|---|---|
| 前端 | 打包产物由 Nginx 直接托管（宝塔面板中的站点） |
| 后端 | uvicorn，只监听 `127.0.0.1:8100`，由 `deploy/restart.sh` 管理进程，Nginx 把 `/api` 转发过来 |
| MySQL | 服务器上已有的实例（宝塔安装），库名 `underleaf` |
| Redis | 服务器上通过 apt 安装，只监听本机 |

与参考项目 taskNote 的流水线相比的改进：

| taskNote 的做法 | 这里的做法 | 原因 |
|---|---|---|
| `npm ci` | `pnpm install --frozen-lockfile` | 本项目用 pnpm，没有 `package-lock.json` |
| 上传整个工作目录（含 `node_modules`） | 只上传 `release/`（前端产物 + 后端代码 + 部署脚本，约 20MB） | 制品小，上传下载快 |
| 先 `rm -rf` 旧目录再解压 | 解压到新的版本目录，最后切换 `current` 软链接 | 切换前线上一直可用；保留最近 5 个版本，可以秒级回滚 |
| 无检查 | 构建前执行 ESLint 和类型检查 | 有问题的代码不会被部署 |
| 重启后不检查 | 健康检查失败自动回滚 | 部署坏版本时线上不中断 |
| 无数据库迁移 | 重启前执行 `alembic upgrade head` | 迁移失败则中止，旧版本继续运行 |

## 服务器目录结构

```
/home/ubuntu/servers/underleaf/
├── releases/
│   ├── 20261108-195311/        每次部署解压出的版本，保留最近 5 个
│   │   ├── backend/            后端代码（.env、.pdm-python 链接到 shared）
│   │   ├── frontend/dist/      前端产物
│   │   ├── deploy/             deploy.sh、restart.sh
│   │   └── VERSION             对应的提交号和构建时间
│   └── ...
├── current -> releases/20261108-195311    当前版本，Nginx 和后端都从这里读取
└── shared/                     跨版本共享，部署时不会被覆盖
    ├── .env                    正式环境配置（数据库、Redis 密码等）
    ├── venv/                   Python 虚拟环境，依赖有变化时才安装
    ├── uploads/                上传的图片
    ├── git/                    Git 同步的裸仓库 {user_id}.git
    ├── logs/underleaf.log      后端日志
    └── underleaf.pid
```

## 一、服务器准备（只需做一次）

服务器：`ubuntu@124.223.10.25`（Ubuntu 24.04，2 核 2GB，装有宝塔面板）。

### 1. Redis（已完成）

- 通过 `apt install redis-server` 安装，开机自启
- 只监听 `127.0.0.1`，已设置密码（`/etc/redis/redis.conf` 中的 `requirepass`），最大内存 64MB
- 该机器上 Redis 官方 systemd 配置中的 `NoExecPaths=/` 会导致启动失败（`libjemalloc.so.2: failed to map segment`），已在 `/etc/systemd/system/redis-server.service.d/override.conf` 中取消该限制
- 常用命令：`sudo systemctl status redis-server`、`redis-cli -a <密码> ping`

### 2. 部署目录和虚拟环境（已完成）

按服务器的惯例（见 `some_web.md`）：Python 3.12 解释器来自 miniforge 的 `py312` 环境，虚拟环境放在 `~/venv` 下，pdm 通过 pipx 安装在 `~/.local/bin`。

```bash
mkdir -p /home/ubuntu/servers/underleaf/shared/logs /home/ubuntu/servers/underleaf/releases
~/miniforge3/envs/py312/bin/python -m venv ~/venv/underleaf-venv-py312
ln -sfn ~/venv/underleaf-venv-py312 /home/ubuntu/servers/underleaf/shared/venv
```

- 不用 `pdm venv create`：它生成的虚拟环境名带有项目目录路径的哈希，而每次部署的版本目录都不同；这里固定一个虚拟环境，各版本通过 `.pdm-python` 共用
- 系统自带的 `python3.12` 缺少 `venv` 模块，不要用它创建

### 3. 正式环境配置 `/home/ubuntu/servers/underleaf/shared/.env`

```bash
APP_ENV=prod
DATABASE_URL=mysql+aiomysql://underleaf_app:<密码>@127.0.0.1:3306/underleaf
REDIS_URL=redis://:<Redis 密码>@127.0.0.1:6379/0
PORT=8100
# 服务器只有 2GB 内存，worker 不宜多
WORKERS=2
# PDF 导出：Chromium 通过本机 Nginx 访问前端渲染页
EXPORT_RENDER_URL=http://127.0.0.1:10002
# 上传的图片（跨版本共享，部署和回滚不影响），见 docs/images.md
UPLOAD_DIR=/home/ubuntu/servers/underleaf/shared/uploads
# Git 同步的裸仓库（跨版本共享；只是数据库的镜像，丢失后会重新生成，但用户需要重新 clone）
GIT_REPO_DIR=/home/ubuntu/servers/underleaf/shared/git
# 登录：JWT 签名密钥（必填，生成方法见 backend/.env.example）；启用 HTTPS 后 COOKIE_SECURE=true
JWT_SECRET=<随机字符串>
COOKIE_SECURE=false
# 发送验证码的邮箱（APP_ENV=prod 时未配置会拒绝发送）
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USERNAME=<邮箱>
SMTP_PASSWORD=<授权码>
SMTP_FROM=Underleaf <邮箱>
```

```bash
chmod 600 /home/ubuntu/servers/underleaf/shared/.env
```

程序使用单独的数据库账号 `underleaf_app`（已创建），只授予 `underleaf` 库的权限。宝塔建库时生成的 `underleaf` 账号保持不变，供你在面板中管理使用：

```sql
-- MySQL 客户端：/www/server/mysql/bin/mysql -uroot -p -S /tmp/mysql.sock
CREATE USER 'underleaf_app'@'127.0.0.1' IDENTIFIED BY '<密码>';
CREATE USER 'underleaf_app'@'localhost' IDENTIFIED BY '<密码>';
GRANT ALL PRIVILEGES ON underleaf.* TO 'underleaf_app'@'127.0.0.1';
GRANT ALL PRIVILEGES ON underleaf.* TO 'underleaf_app'@'localhost';
```

### 4. Nginx 站点（已完成）

与 some_web（10001 端口）一样按 IP + 端口访问，Underleaf 使用 **10002** 端口：

- 配置文件：`/www/server/panel/vhost/nginx/underleaf.conf`（宝塔会自动加载该目录下的 `*.conf`）。这是手动创建的，不会出现在宝塔的站点列表中，修改后执行 `sudo /www/server/nginx/sbin/nginx -t && sudo /www/server/nginx/sbin/nginx -s reload`
- 防火墙：服务器 ufw 已放行 10002；**腾讯云控制台的防火墙需要手动放行 TCP 10002**（两层防火墙都放行才能访问）
- `/home/ubuntu` 的权限为 755，Nginx 的 www 用户可以读取其中的前端产物（见 `some_web.md`「问题解决」）

配置的主要内容：

```nginx
listen 10002;
root /home/ubuntu/servers/underleaf/current/frontend/dist;
index index.html;

# 前端路由（/notes/1、/s/xxx 等）回退到 index.html
location / {
    try_files $uri $uri/ /index.html;
    add_header Cache-Control "no-cache";     # index.html 不缓存，发布后立刻生效
}

# 打包产物文件名带哈希，可以长期缓存
location /assets/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}

location ^~ /api/ {
    proxy_pass http://127.0.0.1:8100;      # 末尾不加 /，保留 /api 前缀
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;     # 导出 PDF 可能需要十几秒
    client_max_body_size 11m;   # 上传图片（上限 10MB）、导出时上传整篇正文（上限 5MB）；Nginx 默认只允许 1MB
}

# Git 同步（git clone / pull / push）：push 的请求体更大，响应不缓冲
location ^~ /api/v1/git/ {
    proxy_pass http://127.0.0.1:8100;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
    proxy_request_buffering on;  # git 大推送用分块传输，先完整接收再转发
    client_max_body_size 51m;    # 后端 GIT_MAX_PUSH_BYTES 默认 50MB
}
```

- Git 仓库目录：`mkdir -p /home/ubuntu/servers/underleaf/shared/git`（后端进程要有读写权限）

- 上传的图片由 Nginx 直接提供，配置见 [images.md](images.md)「服务器配置」
- 登录接口按 IP 限流（`limit_req`）等登录功能完成后再加

### 5. 导出 PDF 所需依赖（尚未执行，下次部署前执行）

```bash
sudo apt install -y fonts-noto-cjk fonts-noto-color-emoji     # 中文和 emoji 字体，否则 PDF 中文显示为方块
sudo /home/ubuntu/servers/underleaf/shared/venv/bin/playwright install-deps chromium
/home/ubuntu/servers/underleaf/shared/venv/bin/playwright install chromium
```

### 6. 云效主机组

这台服务器在搭建 some_web 时已经安装过云效 Runner（见 `some_web.md`），可以直接复用已有的腾讯云主机组；如果新建，选择 runner 方式，把页面给出的安装命令复制到服务器上执行。

## 二、流水线配置

「新建流水线」→ 选「YAML 化编排」（或先选空模板的可视化编排，再切换到 YAML），粘贴下面的内容，替换 `<...>` 部分：

```yaml
sources:
  repo_0:
    type: codeup
    name: underleaf
    endpoint: https://codeup.aliyun.com/<组织 ID>/<路径>/underleaf.git
    branch: main
    branchFilter: main
    triggerEvents: push          # 推送到 main 自动执行；去掉则只能手动运行
    certificate:
      type: serviceConnection
      serviceConnection: <代码源服务连接 ID>   # 同一组织下可以沿用 taskNote 的
defaultWorkspace: repo_0
stages:
  stage_0:
    name: 构建
    jobs:
      job_0:
        name: 构建打包
        runsOn:
          group: public/cn-beijing
        steps:
          step_0:
            name: 检查、构建与打包
            step: NodeBuild
            with:
              versionType: custom
              customNodeVersion: '22.12'
              nodeVersion: '22.12'
              useCache: true
              run: |-
                cd frontend
                npm install -g pnpm@10
                pnpm install --frozen-lockfile
                pnpm exec eslint .      # 不用 pnpm lint，它带 --fix，会改代码而不是报错
                pnpm build              # 包含 vue-tsc 类型检查
                cd ..
                bash deploy/package.sh
          step_1:
            name: 构建物上传
            step: ArtifactUpload
            with:
              artifact: Artifacts_${PIPELINE_ID}
              includePathInArtifact: false
              repo: flow_generic_repo
              filePath:
              - release
              uploadType: packages
              version: ${DATETIME}
              serviceConnection: <制品仓库服务连接 ID>   # 同一组织下可以沿用 taskNote 的
        driven: auto
        plugins: []
  stage_1:
    name: 部署
    jobs:
      job_0:
        name: 主机部署
        component: VMDeploy
        driven: auto
        with:
          downloadArtifact: true
          artifact: $[stages.stage_0.job_0.step_1.artifacts.Artifacts_${PIPELINE_ID}]
          useEncode: false
          machineGroup: <主机组 ID>
          artifactDownloadPath: /home/ubuntu/servers/underleaf/underleaf-package.tgz
          executeUser: ubuntu
          batchNumber: 1
          run: |-
            set -e
            # 部署脚本在制品里，先解压到临时目录取出来，再由它完成正式部署
            TMP=$(mktemp -d)
            tar xzf /home/ubuntu/servers/underleaf/underleaf-package.tgz -C "$TMP"
            DEPLOY=$(find "$TMP" -path '*/deploy/deploy.sh' | head -1)
            cp "$DEPLOY" /home/ubuntu/servers/underleaf/deploy.sh
            rm -rf "$TMP"
            bash /home/ubuntu/servers/underleaf/deploy.sh /home/ubuntu/servers/underleaf/underleaf-package.tgz
        plugins: []
```

说明：

- **构建集群**：`public/cn-beijing` 为云效北京公共构建集群
- **制品内容**：`deploy/package.sh` 把 `frontend/dist`、后端代码（不含 tests、.venv、.env）、`deploy/` 收集到 `release/`，并写入 `VERSION`（提交号、构建时间）
- **单批部署**：只有一台服务器，`batchNumber: 1`，不需要 taskNote 那样的分批暂停
- **后端检查**：目前构建阶段只检查前端。后端的 ruff / pyright / pytest 需要 Python 3.12 环境，可以在可视化编排中为「构建」阶段再加一个并行任务，选 Python 构建步骤，命令：
  ```bash
  cd backend && pip install pdm && pdm install --frozen-lockfile
  pdm run ruff check . && pdm run ruff format --check . && pdm run pyright && pdm run pytest
  ```

搭好并成功运行后，把云效中最终的 YAML 复制到本文末尾留档。

## 三、日常使用

- **发布**：合并到 `main` 自动执行；在流水线运行记录中查看每一步的日志
- **查看线上版本**：`bash /home/ubuntu/servers/underleaf/current/deploy/restart.sh status`（显示进程状态和 `VERSION` 中的提交号）
- **查看日志**：`bash /home/ubuntu/servers/underleaf/current/deploy/restart.sh logs`
- **手动重启**：`bash /home/ubuntu/servers/underleaf/current/deploy/restart.sh restart`
- **修改配置**：编辑 `/home/ubuntu/servers/underleaf/shared/.env` 后手动重启，不需要重新运行流水线

## 四、回滚

**自动回滚**：部署后 60 秒内健康检查（`/api/v1/health`）不通过，`deploy.sh` 会自动切回上一个版本并重启，流水线标记为失败。

**手动回滚**到任意保留的版本：

```bash
cd /home/ubuntu/servers/underleaf
ls -t releases/                                      # 最近 5 个版本，最新的在前
cat releases/<版本>/VERSION                          # 确认对应的提交
ln -sfn /home/ubuntu/servers/underleaf/releases/<版本> current.tmp && mv -T current.tmp current
bash current/deploy/restart.sh restart
```

注意：

- **回滚不会撤销数据库迁移**。修改表结构时尽量只做向后兼容的改动（新增字段带默认值、先加后删），保证旧版本代码能在新表结构上运行
- **虚拟环境是共享的**，回滚不会恢复旧版本的依赖。依赖通常向后兼容，一般没有影响；有问题时在旧版本目录的 `backend/` 下执行 `pdm sync --prod --no-self --clean`

## 五、注意事项

- **线上旧版本的数据**：线上目前运行的是演示模式的旧版本，数据只存在访问者浏览器中，部署新版本后不会保留
- **内存只有 2GB**：后端 worker 默认 2 个；实现 PDF 导出后，Chromium 每次导出会额外占用一两百 MB，届时观察内存，必要时降为 1 个 worker 或增加 swap
- **MySQL 端口**：ufw 中 3306 对所有来源开放。如果不需要从外部直连数据库，建议在 ufw 和腾讯云防火墙中关闭，或限制为指定 IP
- **宝塔面板**：Nginx 和 MySQL 由宝塔管理，修改其配置请在面板中操作，避免被面板覆盖

## 六、手动部署（不经过流水线）

在本地打包、上传，再在服务器上执行部署脚本（与流水线的部署阶段做的是同一件事）：

```bash
# 本地
cd frontend && pnpm build && cd ..
bash deploy/package.sh
tar --no-mac-metadata -czf /tmp/underleaf-package.tgz -C release .   # 不写入 macOS 扩展属性，否则服务器解压时报一堆警告
scp /tmp/underleaf-package.tgz ubuntu@124.223.10.25:/home/ubuntu/servers/underleaf/

# 服务器
ssh ubuntu@124.223.10.25
cd /home/ubuntu/servers/underleaf
tar xzf underleaf-package.tgz ./deploy/deploy.sh -O > deploy.sh
bash deploy.sh /home/ubuntu/servers/underleaf/underleaf-package.tgz
```

`deploy.sh` 会安装依赖、执行数据库迁移、重启后端并做健康检查，失败时自动回滚。

## 七、流水线 YAML 留档

```yaml
# 在云效中成功运行后，把最终的 YAML 粘贴到这里
```
