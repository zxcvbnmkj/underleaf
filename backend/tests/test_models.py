"""验证表结构上的约束：唯一性、生成列、级联删除、默认值。"""

import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Folder, Note, User
from app.models.note import PUBLIC_ID_LENGTH


async def make_user(session: AsyncSession, name: str = "alice") -> User:
    user = User(email=f"{name}@example.com", nickname=name, password_hash="x")
    session.add(user)
    await session.commit()
    return user


async def test_user_defaults_and_case_insensitive_unique(session: AsyncSession) -> None:
    user = await make_user(session)
    assert user.token_version == 0
    assert user.content_rev == 0
    assert user.created_at is not None

    session.add(User(email="ALICE@example.com", nickname="bob", password_hash="x"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    session.add(User(email="bob@example.com", nickname="Alice", password_hash="x"))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_folder_name_unique_in_root(session: AsyncSession) -> None:
    """根目录 parent_id 为 NULL，依靠生成列 parent_key 实现同名限制。"""
    user = await make_user(session)
    session.add(Folder(user_id=user.id, parent_id=None, name="读书"))
    await session.commit()

    session.add(Folder(user_id=user.id, parent_id=None, name="读书"))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_folder_same_name_allowed_in_different_parents(session: AsyncSession) -> None:
    user = await make_user(session)
    other = await make_user(session, "bob")
    a = Folder(user_id=user.id, name="A")
    b = Folder(user_id=user.id, name="B")
    session.add_all([a, b, Folder(user_id=other.id, name="A")])  # 不同用户可以同名
    await session.commit()

    session.add_all(
        [
            Folder(user_id=user.id, parent_id=a.id, name="笔记"),
            Folder(user_id=user.id, parent_id=b.id, name="笔记"),
        ]
    )
    await session.commit()
    assert a.parent_key == 0


async def test_note_defaults(session: AsyncSession) -> None:
    user = await make_user(session)
    note = Note(user_id=user.id, title="欢迎 🎉")
    session.add(note)
    await session.commit()

    assert note.version == 1
    assert note.is_public is False
    assert note.content == ""
    assert len(note.public_id) == PUBLIC_ID_LENGTH
    assert note.folder_key == 0
    assert note.title == "欢迎 🎉"  # utf8mb4 能存 emoji


async def test_updated_at_refreshes_on_update(session: AsyncSession) -> None:
    user = await make_user(session)
    note = Note(user_id=user.id, title="t")
    session.add(note)
    await session.commit()
    before = note.updated_at

    await asyncio.sleep(0.01)
    note.content = "changed"
    await session.commit()
    assert note.updated_at > before
    assert note.created_at <= before


async def test_move_note_to_root_with_duplicate_title_rejected(session: AsyncSession) -> None:
    user = await make_user(session)
    folder = Folder(user_id=user.id, name="F")
    session.add(folder)
    await session.commit()
    session.add_all(
        [
            Note(user_id=user.id, title="同名"),
            inner := Note(user_id=user.id, folder_id=folder.id, title="同名"),
        ]
    )
    await session.commit()

    inner.folder_id = None
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_delete_folder_cascades(session: AsyncSession) -> None:
    user = await make_user(session)
    top = Folder(user_id=user.id, name="top")
    session.add(top)
    await session.commit()
    child = Folder(user_id=user.id, parent_id=top.id, name="child")
    session.add(child)
    await session.commit()
    session.add_all(
        [
            Note(user_id=user.id, folder_id=top.id, title="n1"),
            Note(user_id=user.id, folder_id=child.id, title="n2"),
            Note(user_id=user.id, title="keep"),
        ]
    )
    await session.commit()

    await session.delete(top)
    await session.commit()

    assert await session.scalar(select(func.count()).select_from(Folder)) == 0
    titles = (await session.scalars(select(Note.title))).all()
    assert titles == ["keep"]
