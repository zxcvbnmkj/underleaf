# 图片存储与迁移

记录图片怎么上传、存在哪里、换服务器时怎么迁移，以及如何清理不再使用的图片。

## 设计要点

- **存在服务器本机磁盘**，不使用对象存储
- **Markdown 中只写站内相对地址**：`![image](/uploads/images/2026/11/3f2a….png)`，**不包含域名或 IP**
  - 浏览器按当前访问的网站加载图片，所以换服务器、换 IP、绑定域名、加 HTTPS 后，**笔记内容都不需要修改**，只要把图片文件一起搬过去
  - 不要在笔记里手写 `http://124.223.10.25:10002/uploads/...` 这样的完整地址，否则换服务器后这些图片会失效
- **图片全部公开**：知道地址就能访问，文件名是 32 位随机字符串，无法猜测
- **只接受 PNG / JPG / GIF / WebP**，按文件头判断格式（不信任扩展名）；不接受 SVG（其中可以嵌入脚本）；单张不超过 10MB

## 上传流程

```
在编辑器中粘贴或拖入图片
  → 光标处插入占位文字「![上传中…（编号）]()」
  → POST /api/v1/images（请求体为图片的二进制内容）
  → 后端校验格式和大小，保存到 UPLOAD_DIR/images/年/月/随机名.扩展名，并在 image 表中记一条记录
  → 返回 { url: "/uploads/images/…" }，前端把占位文字替换为 ![文件名](url)
```

- 图片单独成段（前后有文字时自动补空行）
- 上传失败时删除占位文字并提示原因
- 上传期间可以继续编辑

## 文件位置

| 环境 | 上传目录 | 谁提供 `/uploads/` 访问 |
|---|---|---|
| 本地开发 | `backend/.env` 中 `UPLOAD_DIR` 指定的目录，未指定时为仓库根目录下的 `uploads/`（已加入 `.gitignore`） | 后端（Vite 开发服务器把 `/uploads` 代理到后端） |
| 服务器 | `/home/ubuntu/data/underleaf/uploads/` | Nginx 直接读取磁盘 |

服务器上通过 `/home/ubuntu/data/underleaf/.env` 中的 `UPLOAD_DIR` 指定上传目录。它在数据目录下，而部署目录 `/home/ubuntu/servers/underleaf` 每次部署都会整个清空重建，**图片不能放在部署目录中**。

服务器上的目录结构：

```
/home/ubuntu/data/underleaf/uploads/
└── images/
    └── 2026/
        └── 11/
            ├── 3f2a9c….png
            └── b25ae4….jpg
```

数据库 `image` 表记录每张图片：`path`（相对上传目录的路径）、`mime`、`size`、`user_id`（登录功能完成后记录上传者）、`created_at`。

## 服务器配置（已完成，2026-11-09）

1. 创建目录并在 `.env` 中指定：
   ```bash
   mkdir -p /home/ubuntu/data/underleaf/uploads
   echo 'UPLOAD_DIR=/home/ubuntu/data/underleaf/uploads' >> /home/ubuntu/data/underleaf/.env
   ```
2. 在 Nginx 配置（`/www/server/panel/vhost/nginx/underleaf.conf`）中加入：
   ```nginx
   # 上传的图片：文件名随机且不会被覆盖，可以长期缓存
   location ^~ /uploads/ {
       alias /home/ubuntu/data/underleaf/uploads/;
       expires 30d;
       add_header Cache-Control "public, immutable";
       add_header X-Content-Type-Options nosniff;   # 禁止浏览器按内容猜测类型
   }
   ```
   并把 `/api/` 中的 `client_max_body_size` 调到 `11m`（图片上限 10MB）
3. 执行数据库迁移（部署脚本会自动执行，新增 `image` 表）
4. 确认 Nginx 的 www 用户能读取上传目录（`/home/ubuntu` 为 755，新建的目录默认 775，通常无需处理）

## 备份

图片只存在这台服务器上，**需要和数据库一起备份**：

```bash
# 图片：增量同步到备份位置（可以是另一台机器）
rsync -a /home/ubuntu/data/underleaf/uploads/ <备份位置>/underleaf-uploads/

# 数据库
mysqldump -uroot -p --single-transaction --default-character-set=utf8mb4 underleaf > underleaf-$(date +%F).sql
```

## 迁移到新服务器

由于笔记中只有站内相对地址，迁移只需要搬运文件和数据库，**不需要修改任何笔记内容**。

1. **在新服务器上部署好 Underleaf**（按 [pipeline.md](pipeline.md) 的服务器准备），先不对外开放
2. **停止旧服务器上的写入**（避免迁移期间有新上传或新笔记）：
   ```bash
   bash /home/ubuntu/servers/underleaf/restart.sh stop
   ```
3. **迁移数据库**：
   ```bash
   # 旧服务器
   mysqldump -uroot -p --single-transaction --default-character-set=utf8mb4 underleaf > underleaf.sql
   # 新服务器（库需要已创建，字符集 utf8mb4）
   mysql -uroot -p underleaf < underleaf.sql
   ```
4. **迁移图片**（在新服务器上执行，从旧服务器拉取）：
   ```bash
   rsync -av ubuntu@<旧服务器 IP>:/home/ubuntu/data/underleaf/uploads/ \
         /home/ubuntu/data/underleaf/uploads/
   ```
5. **核对**：
   ```bash
   # 文件数量应与旧服务器一致
   find /home/ubuntu/data/underleaf/uploads -type f | wc -l
   # 数据库中的图片记录数
   mysql -uroot -p -N -e "SELECT COUNT(*) FROM underleaf.image"
   # 预览清理脚本：「被引用」的数量应与旧服务器一致，且没有「文件已不存在」的记录
   cd /home/ubuntu/servers/underleaf/backend && ~/.local/bin/pdm run python -m scripts.cleanup_images
   ```
6. **启动新服务器上的后端，切换访问地址**（修改域名解析，或告知新的 IP），打开几篇带图片的笔记和分享链接确认显示正常

### 笔记中存在完整地址时

如果有笔记手写了包含旧域名或 IP 的完整图片地址，迁移后可以批量替换为相对地址（先备份数据库）：

```sql
UPDATE note
SET content = REPLACE(content, 'http://124.223.10.25:10002/uploads/', '/uploads/'),
    version = version + 1
WHERE content LIKE '%http://124.223.10.25:10002/uploads/%';
```

`version` 加 1 是为了让正在打开这些笔记的浏览器在保存时收到冲突提示，而不是用旧内容覆盖。

### 以后改用对象存储（OSS / COS）时

1. 把 `/home/ubuntu/data/underleaf/uploads/` 整个上传到对象存储，保持相同的目录结构
2. 二选一：
   - **不改笔记**（推荐）：Nginx 中把 `/uploads/` 反向代理到对象存储的地址
   - **改笔记**：用上面的 `REPLACE` 把 `/uploads/` 替换为对象存储的完整地址；之后换存储服务商还要再改一次

## 清理不再使用的图片

把图片从笔记中删掉后，图片文件不会自动删除。需要时手动执行清理脚本 `backend/scripts/cleanup_images.py`：

```bash
cd /home/ubuntu/servers/underleaf/backend
~/.local/bin/pdm run python -m scripts.cleanup_images                  # 预览：只列出将要删除的图片
~/.local/bin/pdm run python -m scripts.cleanup_images --apply          # 确认后删除
~/.local/bin/pdm run python -m scripts.cleanup_images --min-age-days 30   # 只清理 30 天前上传的
```

规则：

- **引用**：任意笔记正文中出现 `/uploads/<图片路径>`
- **候选**：`image` 表中的记录，以及上传目录中存在但没有数据库记录的文件（例如保存过程中失败留下的）
- **宽限期**：只删除上传时间早于 `--min-age-days` 天（默认 7 天）的图片。刚粘贴的图片可能还在编辑器或浏览器本地草稿中、尚未保存到服务器，宽限期避免误删
- 删除不可恢复，执行 `--apply` 前建议先按上面的方法备份上传目录

## 导出时的图片

- **PDF**：后端 Chromium 打开渲染页时直接加载图片
- **Word**：后端预先取好图片再交给 Pandoc
  - 站内图片 `/uploads/...` 直接从磁盘读取
  - 公网图片（http / https）全部下载；单张不超过 10MB、单次最多 50 张、单张 10 秒超时
  - 不下载解析到内网 / 本机 / 云服务器元数据等非公网地址的图片（防止借导出读取服务器内部信息）；不读取 `/uploads/` 以外的服务器文件。这些图片在 Word 中显示为图片说明文字
