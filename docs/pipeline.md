# 部署流水线（云效 Flow）

记录 Underleaf 的自动化部署：服务器怎么准备、流水线怎么配置、出问题怎么处理。
不使用 Docker，直接部署在服务器上；只有一个环境（正式环境）。

## 当前部署状态（2026-11-09）

| 项目 | 状态 |
|---|---|
| 访问地址 | `http://124.223.10.25:10002`（需要在腾讯云轻量服务器控制台的防火墙中放行 TCP 10002） |
| 流水线 | 已在云效中配置（构建 → 构建物上传 → 主机部署），推送到 `main` 后执行 |
| 数据库 | MySQL 5.7.44（宝塔安装），库 `underleaf`；程序使用账号 `underleaf_app`（只能从本机访问 `underleaf` 库） |
| Redis | 已安装并运行 |
| Nginx | 已配置（10002 端口），包含 `/uploads/`、`/api/v1/git/` |
| `.env` | 已配置数据库、Redis、`JWT_SECRET`、SMTP、`UPLOAD_DIR`、`GIT_REPO_DIR`、`EXPORT_RENDER_URL` |
| 图片上传、Git 同步 | 目录已创建（`/home/ubuntu/data/underleaf/uploads`、`git`） |
| PDF / Word 导出 | **服务器尚未安装 Chromium 和字体**，见「一、5」；未安装时导出会失败，其他功能不受影响 |

## 总览

```
推送到 main
   ↓
阶段一「构建」（云效构建机）
   pnpm install → ESLint → 类型检查 + 打包
   构建物上传：frontend/dist、backend、restart.sh 打成制品
   ↓
阶段二「部署」（云效主机部署，以 ubuntu 用户登录服务器执行）
   清空部署目录 → 解压 → 链接 .env → 安装依赖 → 数据库迁移 → restart.sh 重启后端
```

| 组件 | 运行方式 |
|---|---|
| 前端 | 打包产物由 Nginx 直接托管 |
| 后端 | uvicorn，只监听 `127.0.0.1:8100`，由仓库根目录的 `restart.sh` 管理进程，Nginx 把 `/api` 转发过来 |
| MySQL | 服务器上已有的实例（宝塔安装），库名 `underleaf` |
| Redis | 服务器上通过 apt 安装，只监听本机 |

## 服务器目录结构

```
/home/ubuntu/servers/underleaf/      部署目录：每次部署整个删除后重建，不要在这里放任何需要保留的东西
├── backend/                         后端代码（.env 链接到数据目录，.pdm-python 指向虚拟环境）
├── frontend/dist/                   前端产物，Nginx 的 root
└── restart.sh                       后端进程管理

/home/ubuntu/data/underleaf/         数据目录：部署时不会动
├── .env                             正式环境配置（数据库、Redis 密码、JWT 密钥、SMTP 等）
├── uploads/                         上传的图片
├── git/                             Git 同步的裸仓库 {user_id}.git
├── logs/underleaf.log               后端日志
└── underleaf.pid

/home/ubuntu/venv/underleaf-venv-py312/   Python 虚拟环境，部署时 pdm sync 只安装有变化的依赖
```

## 一、服务器准备（只需做一次，均已完成）

服务器：`ubuntu@124.223.10.25`（Ubuntu 24.04，2 核 2GB，装有宝塔面板）。

### 1. Redis

- 通过 `apt install redis-server` 安装，开机自启
- 只监听 `127.0.0.1`，已设置密码（`/etc/redis/redis.conf` 中的 `requirepass`），最大内存 64MB
- 该机器上 Redis 官方 systemd 配置中的 `NoExecPaths=/` 会导致启动失败（`libjemalloc.so.2: failed to map segment`），已在 `/etc/systemd/system/redis-server.service.d/override.conf` 中取消该限制
- 常用命令：`sudo systemctl status redis-server`、`redis-cli -a <密码> ping`

### 2. 数据目录和虚拟环境

按服务器的惯例（见 `some_web.md`）：Python 3.12 解释器来自 miniforge 的 `py312` 环境，虚拟环境放在 `~/venv` 下，pdm 安装在 `/usr/local/bin`。

```bash
mkdir -p /home/ubuntu/data/underleaf/{logs,uploads,git}
~/miniforge3/envs/py312/bin/python -m venv ~/venv/underleaf-venv-py312
```

- 不用 `pdm venv create`：它生成的虚拟环境名带有项目目录路径的哈希；这里固定一个虚拟环境，部署时通过 `backend/.pdm-python` 指定
- 系统自带的 `python3.12` 缺少 `venv` 模块，不要用它创建

### 3. 正式环境配置 `/home/ubuntu/data/underleaf/.env`

```bash
APP_ENV=prod
DATABASE_URL=mysql+aiomysql://underleaf_app:<密码>@127.0.0.1:3306/underleaf
REDIS_URL=redis://:<Redis 密码>@127.0.0.1:6379/0
PORT=8100
# 服务器只有 2GB 内存，worker 不宜多
WORKERS=2
# 登录：JWT 签名密钥（必填，否则后端无法启动），修改后所有用户需要重新登录
JWT_SECRET=<随机字符串>
COOKIE_SECURE=false
# 图片上传、Git 同步的数据目录（部署目录每次会被清空，必须放在这里）
UPLOAD_DIR=/home/ubuntu/data/underleaf/uploads
GIT_REPO_DIR=/home/ubuntu/data/underleaf/git
# PDF 导出：Chromium 通过本机 Nginx 访问前端渲染页
EXPORT_RENDER_URL=http://127.0.0.1:10002
# 发送验证码的邮箱（APP_ENV=prod 时未配置会拒绝发送）
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_SSL=true
SMTP_USERNAME=<邮箱>
SMTP_PASSWORD=<授权码>
SMTP_FROM=Underleaf <邮箱>
```

```bash
chmod 600 /home/ubuntu/data/underleaf/.env
```

程序使用单独的数据库账号 `underleaf_app`，只授予 `underleaf` 库的权限。宝塔建库时生成的 `underleaf` 账号保持不变，供你在面板中管理使用：

```sql
-- MySQL 客户端：/www/server/mysql/bin/mysql -uroot -p -S /tmp/mysql.sock
CREATE USER 'underleaf_app'@'127.0.0.1' IDENTIFIED BY '<密码>';
CREATE USER 'underleaf_app'@'localhost' IDENTIFIED BY '<密码>';
GRANT ALL PRIVILEGES ON underleaf.* TO 'underleaf_app'@'127.0.0.1';
GRANT ALL PRIVILEGES ON underleaf.* TO 'underleaf_app'@'localhost';
```

### 4. Nginx 站点

与 some_web（10001 端口）一样按 IP + 端口访问，Underleaf 使用 **10002** 端口：

- 配置文件：`/www/server/panel/vhost/nginx/underleaf.conf`（宝塔会自动加载该目录下的 `*.conf`）。这是手动创建的，不会出现在宝塔的站点列表中，修改后执行 `sudo /www/server/nginx/sbin/nginx -t && sudo /www/server/nginx/sbin/nginx -s reload`
- 防火墙：服务器 ufw 已放行 10002；**腾讯云控制台的防火墙需要手动放行 TCP 10002**（两层防火墙都放行才能访问）
- `/home/ubuntu` 的权限为 755，Nginx 的 www 用户可以读取其中的前端产物和上传的图片

```nginx
server
{
    listen 10002;
    server_name _;
    root /home/ubuntu/servers/underleaf/frontend/dist;
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

    # 上传的图片：文件名随机且不会被覆盖，可以长期缓存
    location ^~ /uploads/ {
        alias /home/ubuntu/data/underleaf/uploads/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        add_header X-Content-Type-Options nosniff;
    }

    location ^~ /api/ {
        proxy_pass http://127.0.0.1:8100;      # 末尾不加 /，保留 /api 前缀
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;     # 导出 PDF 可能需要十几秒
        client_max_body_size 11m;   # 上传图片（上限 10MB）、导出时上传整篇正文（上限 5MB）
        add_header Cache-Control "no-store";
    }

    # Git 同步（git clone / pull / push）：push 的请求体更大
    location ^~ /api/v1/git/ {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_request_buffering on;  # git 大推送用分块传输，先完整接收再转发
        client_max_body_size 51m;    # 后端 GIT_MAX_PUSH_BYTES 默认 50MB
        add_header Cache-Control "no-store";
    }

    access_log  /www/wwwlogs/underleaf.log;
    error_log  /www/wwwlogs/underleaf.error.log;
}
```

- 修改前的旧配置备份在 `/home/ubuntu/data/underleaf/underleaf.conf.bak-20261109`
- 登录接口按 IP 限流目前由后端（Redis 计数）实现，Nginx 未加 `limit_req`

### 5. 导出 PDF 所需依赖（尚未执行）

```bash
sudo apt install -y fonts-noto-cjk fonts-noto-color-emoji     # 中文和 emoji 字体，否则 PDF 中文显示为方块
sudo /home/ubuntu/venv/underleaf-venv-py312/bin/playwright install-deps chromium
/home/ubuntu/venv/underleaf-venv-py312/bin/playwright install chromium
```

### 6. 云效主机组

这台服务器在搭建 some_web 时已经安装过云效 Runner（见 `some_web.md`），复用已有的腾讯云主机组。

## 二、流水线配置

在云效中用可视化编排配置，三个步骤：

### 1. 构建（Node.js 构建）

- Node 版本：22.12 或更高（Vite 8 要求 `^20.19.0 || >=22.12.0`）
- 执行命令：

```bash
cd frontend
npm install -g pnpm@10
pnpm install --frozen-lockfile
pnpm exec eslint .      # 不用 pnpm lint，它带 --fix，会改代码而不是报错
pnpm build              # 包含 vue-tsc 类型检查
```

### 2. 构建物上传

- 制品名称：`Artifacts_${PIPELINE_ID}`
- 打包路径：`frontend/dist`、`backend`、`restart.sh`
- **勾选**「制品中包含打包路径的目录」：解压后保持 `frontend/dist/`、`backend/`、`restart.sh` 的结构，`restart.sh` 以自己所在目录为项目根目录

### 3. 主机部署

- 下载路径：`/home/ubuntu/servers/package.tgz`（必须在部署目录外面，否则会被下面的 `rm -fr` 删掉）
- 执行用户：`ubuntu`（pdm、虚拟环境、部署目录都属于 ubuntu）
- 部署脚本：

```bash
set -e
cd /home/ubuntu/servers
rm -fr underleaf
mkdir -v underleaf
mv package.tgz underleaf

cd underleaf
tar zxf package.tgz
ln -s /home/ubuntu/data/underleaf/.env backend/.env
echo '/home/ubuntu/venv/underleaf-venv-py312/bin/python' > backend/.pdm-python

cd backend
pdm sync --prod --no-self
pdm run alembic upgrade head

cd ..
bash restart.sh restart
```

- `set -e`：安装依赖或数据库迁移失败时立即停止，流水线标记为失败
- `restart.sh` 内部用 nohup 在后台启动 uvicorn，不需要再套一层 nohup

## 三、日常使用

- **发布**：推送到 `main` 自动执行；在流水线运行记录中查看每一步的日志
- **查看状态**：`bash /home/ubuntu/servers/underleaf/restart.sh status`
- **查看日志**：`bash /home/ubuntu/servers/underleaf/restart.sh logs`
- **手动重启**：`bash /home/ubuntu/servers/underleaf/restart.sh restart`
- **修改配置**：编辑 `/home/ubuntu/data/underleaf/.env` 后手动重启，不需要重新运行流水线

## 四、出问题时

部署脚本没有健康检查和自动回滚：

- **部署中途失败**（依赖安装、数据库迁移出错）：部署目录已被清空，网站不可用。修复后重新运行流水线
- **部署成功但后端起不来**：`restart.sh logs` 查看原因（常见为 `.env` 缺少配置项）
- **回退到旧版本**：在云效中选择旧的运行记录重新执行，或 `git revert` 后推送

注意：**回退不会撤销数据库迁移**。修改表结构时尽量只做向后兼容的改动（新增字段带默认值、先加后删），保证旧版本代码能在新表结构上运行。

## 五、注意事项

- **部署期间短暂不可用**：部署脚本先删除旧目录，到新版本启动完成前（通常几十秒）网站无法访问
- **内存只有 2GB**：后端 worker 默认 2 个；PDF 导出时 Chromium 每次额外占用一两百 MB，观察内存，必要时降为 1 个 worker 或增加 swap
- **MySQL 端口**：ufw 中 3306 对所有来源开放。如果不需要从外部直连数据库，建议在 ufw 和腾讯云防火墙中关闭，或限制为指定 IP
- **宝塔面板**：MySQL 由宝塔管理，修改其配置请在面板中操作，避免被面板覆盖
