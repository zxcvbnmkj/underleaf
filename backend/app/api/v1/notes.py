"""笔记：列表（不含正文）、最近编辑（带摘要）、全文搜索、详情、新建、修改元信息、保存正文（乐观锁）、删除；以及公开分享。"""

from fastapi import APIRouter, Query
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import defer

from app.api.deps import CurrentUser, Session
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Note, User
from app.schemas.notes import (
    AuthorOut,
    ContentSave,
    NoteCreate,
    NoteMetaOut,
    NoteOut,
    NoteUpdate,
    RecentNoteOut,
    SharedNoteOut,
)
from app.services.excerpt import make_excerpt, make_snippet
from app.services.names import clean_name
from app.services.notes import (
    bump_content_rev,
    own_folder,
    own_note,
    save_changes,
    unique_title,
)

router = APIRouter(prefix="/notes", tags=["notes"])
share_router = APIRouter(prefix="/share", tags=["share"])

TITLE_TAKEN = "同一文件夹下已有同名笔记"


@router.get("", response_model=list[NoteMetaOut])
async def list_notes(user: CurrentUser, session: Session) -> list[Note]:
    rows = await session.scalars(
        select(Note).options(defer(Note.content)).where(Note.user_id == user.id)
    )
    return list(rows)


# 摘要只需要正文开头：数据库只截取这么多字符，避免读出整篇（正文上限 5MB）
_EXCERPT_SOURCE_CHARS = 1000


@router.get("/recent", response_model=list[RecentNoteOut])
async def recent_notes(
    user: CurrentUser, session: Session, limit: int = Query(8, ge=1, le=20)
) -> list[RecentNoteOut]:
    """最近编辑的笔记，按更新时间倒序，带正文开头的纯文本摘要。"""
    rows = await session.execute(
        select(Note, func.left(Note.content, _EXCERPT_SOURCE_CHARS))
        .options(defer(Note.content))
        .where(Note.user_id == user.id)
        .order_by(Note.updated_at.desc(), Note.id.desc())
        .limit(limit)
    )
    return [
        RecentNoteOut(
            **NoteMetaOut.model_validate(note, from_attributes=True).model_dump(),
            excerpt=make_excerpt(head or ""),
        )
        for note, head in rows.tuples()
    ]


# 搜索摘要：从第一个关键词命中处往前留这么多字符开始截取（去掉 Markdown 标记前的原文长度）
_SNIPPET_BEFORE = 200
_MAX_TERMS = 5


@router.get("/search", response_model=list[RecentNoteOut])
async def search_notes(
    user: CurrentUser,
    session: Session,
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(30, ge=1, le=50),
) -> list[RecentNoteOut]:
    """全文搜索：按空格分成多个关键词，每个关键词都要出现在标题或正文中（不区分大小写）。

    结果按更新时间倒序，摘要取第一个关键词在正文中命中处附近的文字。
    """
    terms = list(dict.fromkeys(q.split()))[:_MAX_TERMS]
    if not terms:
        return []
    # 第一个关键词在正文中的位置（1 起，未命中为 0），只把附近一段读出来
    pos = func.locate(terms[0], Note.content)
    start = func.greatest(pos - _SNIPPET_BEFORE, 1)
    rows = await session.execute(
        select(Note, start, func.substring(Note.content, start, _EXCERPT_SOURCE_CHARS))
        .options(defer(Note.content))
        .where(
            Note.user_id == user.id,
            and_(
                *(
                    or_(
                        Note.title.contains(t, autoescape=True),
                        Note.content.contains(t, autoescape=True),
                    )
                    for t in terms
                )
            ),
        )
        .order_by(Note.updated_at.desc(), Note.id.desc())
        .limit(limit)
    )
    return [
        RecentNoteOut(
            **NoteMetaOut.model_validate(note, from_attributes=True).model_dump(),
            excerpt=make_snippet(part or "", terms, clipped=offset > 1),
        )
        for note, offset, part in rows.tuples()
    ]


@router.post("", response_model=NoteOut)
async def create_note(body: NoteCreate, user: CurrentUser, session: Session) -> Note:
    """新建笔记。同一文件夹下已有同名笔记时自动在标题后加序号（未命名笔记 2）。"""
    if body.folder_id is not None:
        await own_folder(session, user.id, body.folder_id)
    title = await unique_title(session, user.id, body.folder_id, clean_name(body.title, "标题"))
    note = Note(user_id=user.id, folder_id=body.folder_id, title=title, content="")
    session.add(note)
    await save_changes(session, user.id, TITLE_TAKEN)
    return note


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: int, user: CurrentUser, session: Session) -> Note:
    return await own_note(session, user.id, note_id)


@router.patch("/{note_id}", response_model=NoteMetaOut)
async def update_note(note_id: int, body: NoteUpdate, user: CurrentUser, session: Session) -> Note:
    """修改标题、移动（folderId 为 null 表示移到根目录）、开关公开分享。不改变版本号。"""
    note = await own_note(session, user.id, note_id)
    changed = False
    if body.title is not None:
        note.title = clean_name(body.title, "标题")
        changed = True
    if "folder_id" in body.model_fields_set and body.folder_id != note.folder_id:
        if body.folder_id is not None:
            await own_folder(session, user.id, body.folder_id)
        note.folder_id = body.folder_id
        changed = True
    if body.is_public is not None:
        note.is_public = body.is_public  # 只是分享开关，不算内容变动
    await save_changes(session, user.id, TITLE_TAKEN, content_changed=changed)
    await session.refresh(note)
    return note


@router.put("/{note_id}/content", response_model=NoteMetaOut)
async def save_content(
    note_id: int, body: ContentSave, user: CurrentUser, session: Session
) -> Note:
    """保存正文，带乐观锁：只有 version 与数据库一致时才更新并加 1，否则返回 409。"""
    limit = get_settings().note_max_bytes
    if len(body.content.encode()) > limit:
        raise AppError(413, "content_too_large", f"笔记内容不能超过 {limit // 1024 // 1024}MB")

    result = await session.execute(
        update(Note)
        .where(Note.id == note_id, Note.user_id == user.id, Note.version == body.version)
        .values(content=body.content, version=Note.version + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:  # pyright: ignore[reportAttributeAccessIssue]
        await own_note(session, user.id, note_id)  # 不存在时返回 404
        raise AppError(409, "version_conflict", "这篇笔记已在其他设备上修改")
    await bump_content_rev(session, user.id)
    await session.commit()
    note = await own_note(session, user.id, note_id)
    await session.refresh(note)
    return note


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: int, user: CurrentUser, session: Session) -> None:
    note = await own_note(session, user.id, note_id)
    await session.delete(note)
    await save_changes(session, user.id, TITLE_TAKEN)


@share_router.get("/{public_id}", response_model=SharedNoteOut)
async def get_shared(public_id: str, session: Session) -> SharedNoteOut:
    """公开分享（无需登录）。未公开或不存在都返回 404；作者只返回昵称，不返回邮箱。"""
    row = (
        await session.execute(
            select(Note, User.nickname)
            .join(User, User.id == Note.user_id)
            .where(Note.public_id == public_id, Note.is_public.is_(True))
        )
    ).first()
    if row is None:
        raise AppError(404, "not_found", "分享不存在或已关闭")
    note, nickname = row
    return SharedNoteOut(
        title=note.title,
        content=note.content,
        created_at=note.created_at,
        updated_at=note.updated_at,
        author=AuthorOut(nickname=nickname),
    )
