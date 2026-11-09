"""Markdown 摘要（首页「最近编辑」卡片、全文搜索结果）。"""

import pytest

from app.services.excerpt import make_excerpt, make_snippet


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("", ""),
        ("# 标题\n\n正文", "标题 正文"),
        ("**加粗** *斜体* ~~删除~~ `代码`", "加粗 斜体 删除 代码"),
        ("见[文档](http://x)，图![示意](/uploads/a.png)略", "见文档，图略"),
        ("- [x] 任务\n1. 第一\n> 引用", "任务 第一 引用"),
        ("| a | b |\n|:--|--:|\n| 1 | 2 |", "a b 1 2"),
        ("---\ntags: x\n---\n正文\n\n---\n\n下一节", "正文 下一节"),
        ("```python\nprint(1)\n```", "print(1)"),
        ("<div>HTML</div><!-- 注释 -->", "HTML"),
        ("a - b", "a - b"),
    ],
)
def test_strip_markdown(markdown: str, expected: str):
    assert make_excerpt(markdown) == expected


def test_truncate():
    assert make_excerpt("字" * 200, limit=10) == "字" * 10 + "…"
    assert make_excerpt("字" * 10, limit=10) == "字" * 10


def test_snippet_around_match():
    text = "甲" * 100 + "**关键词**" + "乙" * 100
    expected = "…" + "甲" * 5 + "关键词" + "乙" * 22 + "…"
    assert make_snippet(text, ["关键词"], limit=30, lead=5) == expected
    # 命中在开头：不加前省略号
    assert make_snippet("关键词在前", ["关键词"]) == "关键词在前"


def test_snippet_case_insensitive_and_fallback():
    assert make_snippet("abc Hello", ["hello"], lead=2) == "…c Hello"
    # 只在链接地址里命中，纯文本中找不到：从头截取
    assert make_snippet("见[文档](http://key)", ["key"]) == "见文档"
    # 传入的是正文中间截出的片段
    assert make_snippet("中间一段", ["无"], clipped=True) == "…中间一段"
