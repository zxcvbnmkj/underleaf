from pydantic import Field

from app.schemas.base import Schema
from app.schemas.common import UtcDatetime


class FolderOut(Schema):
    id: int
    name: str
    parent_id: int | None


class FolderCreate(Schema):
    name: str
    parent_id: int | None = None


class FolderUpdate(Schema):
    """只更新传了的字段；parentId 传 null 表示移到根目录。"""

    name: str | None = None
    parent_id: int | None = None


class NoteMetaOut(Schema):
    id: int
    title: str
    folder_id: int | None
    is_public: bool
    public_id: str
    version: int
    created_at: UtcDatetime
    updated_at: UtcDatetime


class NoteOut(NoteMetaOut):
    content: str


class NoteCreate(Schema):
    title: str = "未命名笔记"
    folder_id: int | None = None


class NoteUpdate(Schema):
    """修改元信息（标题、所在文件夹、是否公开），不涉及版本号。folderId 传 null 表示移到根目录。"""

    title: str | None = None
    folder_id: int | None = None
    is_public: bool | None = None


class ContentSave(Schema):
    content: str
    version: int = Field(ge=1)


class AuthorOut(Schema):
    nickname: str


class SharedNoteOut(Schema):
    title: str
    content: str
    created_at: UtcDatetime
    updated_at: UtcDatetime
    author: AuthorOut
