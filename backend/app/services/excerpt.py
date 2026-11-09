"""从 Markdown 正文生成纯文本摘要（首页「最近编辑」卡片使用）。

只做粗略的去标记：目的是让卡片上显示可读的文字，不追求与渲染结果完全一致。
"""

import re

# 去掉整块内容：YAML front matter、HTML 注释
_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
# 代码块围栏行本身去掉，块内代码保留（代码笔记也能看出内容）
_FENCE = re.compile(r"^\s*(```|~~~).*$", re.M)
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_REF_LINK_DEF = re.compile(r"^\s*\[[^\]]+\]:\s*\S+.*$", re.M)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
# 行首标记：标题、引用、列表、任务框
_LINE_PREFIX = re.compile(r"^\s*(?:#{1,6}\s+|>+\s?|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)", re.M)
# 分隔线、表格的对齐行
_RULE = re.compile(r"^\s*(?:[-*_]\s*){3,}$", re.M)
_TABLE_ALIGN = re.compile(r"^(?=.*\|)[\s|:-]*-[\s|:-]*$", re.M)  # 至少含一个 |，如 |:--|--:|
# 强调、删除线、行内代码的标记符
_EMPHASIS = re.compile(r"(\*{1,3}|_{2,3}|~~|`+)")
_WHITESPACE = re.compile(r"\s+")


def make_excerpt(markdown: str, limit: int = 120) -> str:
    text = _FRONT_MATTER.sub("", markdown.replace("\r\n", "\n"))
    text = _HTML_COMMENT.sub("", text)
    text = _FENCE.sub("", text)
    text = _IMAGE.sub("", text)  # 图片不出现在摘要中
    text = _LINK.sub(r"\1", text)
    text = _REF_LINK_DEF.sub("", text)
    text = _HTML_TAG.sub("", text)
    text = _RULE.sub("", text)
    text = _TABLE_ALIGN.sub("", text)
    text = _LINE_PREFIX.sub("", text)
    text = _EMPHASIS.sub("", text)
    text = text.replace("|", " ")
    text = _WHITESPACE.sub(" ", text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"
