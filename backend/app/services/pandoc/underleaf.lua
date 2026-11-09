--[[
Underleaf：Markdown → Word 时使用的 Pandoc Lua 过滤器。

1. Mermaid 代码块替换为后端用 Chromium 截取的图片（与网页预览一致）
   - 图片放在 UNDERLEAF_MERMAID_DIR 目录下，按文档顺序命名为 mermaid-0.png、mermaid-1.png…
   - UNDERLEAF_MERMAID_WIDTHS 为逗号分隔的显示宽度（像素），0 表示该图渲染失败，保留代码块
   - 图片数量与文档中的 Mermaid 代码块数量不一致时，全部保留为代码块，避免错位
   - 通过 mediabag 提供图片，配合 --sandbox 仍然可用
2. 图片：UNDERLEAF_IMAGE_MAP 指向 JSON 映射文件 {原地址: 本地文件}，由后端预先取好；
   映射中的图片放入 mediabag 替换地址，其余图片保持原样（沙箱中无法读取，Word 中显示说明文字）
3. UNDERLEAF_TITLE 存在时作为文档标题（按纯文本处理）
4. 原始 HTML 按普通文字输出：网页预览禁用了 HTML（显示为文字），Word 中保持一致；
   否则 docx 会直接丢弃这些内容
]]

local dir = os.getenv('UNDERLEAF_MERMAID_DIR')
local widths = {}
for w in string.gmatch(os.getenv('UNDERLEAF_MERMAID_WIDTHS') or '', '[^,]+') do
  table.insert(widths, tonumber(w) or 0)
end

local function is_mermaid(el)
  return el.classes:includes('mermaid')
end

local function replace_mermaid(doc)
  local total = 0
  doc:walk({ CodeBlock = function(el) if is_mermaid(el) then total = total + 1 end end })
  if dir == nil or total == 0 or total ~= #widths then
    return doc
  end

  local index = 0
  return doc:walk({
    CodeBlock = function(el)
      if not is_mermaid(el) then return nil end
      local i = index
      index = index + 1
      local width = widths[i + 1]
      if width == nil or width <= 0 then return nil end
      local name = 'mermaid-' .. i .. '.png'
      local f = io.open(dir .. '/' .. name, 'rb')
      if f == nil then return nil end
      local data = f:read('a')
      f:close()
      pandoc.mediabag.insert(name, 'image/png', data)
      -- 过宽的图片 Pandoc 会自动缩放到版心宽度
      return pandoc.Para({ pandoc.Image({}, name, '', { width = width .. 'px' }) })
    end,
  })
end

local function html_as_text(doc)
  return doc:walk({
    RawBlock = function(el)
      if el.format == 'html' then
        return pandoc.Para({ pandoc.Str((el.text:gsub('%s+$', ''))) })
      end
    end,
    RawInline = function(el)
      if el.format == 'html' then
        return pandoc.Str(el.text)
      end
    end,
  })
end

local function replace_images(doc)
  local map_file = os.getenv('UNDERLEAF_IMAGE_MAP')
  if map_file == nil then return doc end
  local f = io.open(map_file, 'r')
  if f == nil then return doc end
  local mapping = pandoc.json.decode(f:read('a'))
  f:close()

  local index = 0
  return doc:walk({
    Image = function(el)
      local path = mapping[el.src]
      if path == nil then return nil end
      local img = io.open(path, 'rb')
      if img == nil then return nil end
      local data = img:read('a')
      img:close()
      index = index + 1
      local ext = path:match('%.(%w+)$') or 'png'
      local name = 'image-' .. index .. '.' .. ext
      local mime = ({ png = 'image/png', jpg = 'image/jpeg', gif = 'image/gif',
                      webp = 'image/webp', svg = 'image/svg+xml' })[ext]
      pandoc.mediabag.insert(name, mime, data)
      el.src = name
      return el
    end,
  })
end

local function set_title(doc)
  local title = os.getenv('UNDERLEAF_TITLE')
  if title and title ~= '' then
    doc.meta.title = pandoc.MetaInlines({ pandoc.Str(title) })
  end
  return doc
end

function Pandoc(doc)
  return set_title(html_as_text(replace_images(replace_mermaid(doc))))
end
