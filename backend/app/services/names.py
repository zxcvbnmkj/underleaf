"""文件夹名和笔记标题的规则（readme「Git 同步 · 兼容约束」）：以后要作为目录名和 `标题.md` 文件名。

- 去掉首尾空白后不能为空
- UTF-8 不超过 240 字节（约 80 个汉字）：文件名上限 255 字节，留出 .md 等余量
- 不能包含 / \\ : * ? " < > | 和控制字符（Windows 最严格的文件名规则）
- 不能是 . 或 ..
"""

import re

from app.core.errors import AppError

MAX_BYTES = 240
_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def clean_name(value: str, what: str) -> str:
    name = value.strip()
    if not name:
        raise AppError(422, "invalid_name", f"{what}不能为空")
    if name in (".", ".."):
        raise AppError(422, "invalid_name", f"{what}不能是 . 或 ..")
    if _ILLEGAL.search(name):
        raise AppError(422, "invalid_name", f'{what}不能包含 / \\ : * ? " < > | 等字符')
    if len(name.encode()) > MAX_BYTES:
        raise AppError(422, "invalid_name", f"{what}太长，最多约 80 个汉字或 240 个英文字符")
    return name
