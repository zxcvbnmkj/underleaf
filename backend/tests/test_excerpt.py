"""Markdown 摘要（首页「最近编辑」卡片）。"""

import pytest

from app.services.excerpt import make_excerpt


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
