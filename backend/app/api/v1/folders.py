"""文件夹：扁平列表由前端组装成树；删除时级联删除子文件夹和其中的笔记（数据库外键 CASCADE）。"""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, Session
from app.core.errors import AppError
from app.models import Folder
from app.schemas.notes import FolderCreate, FolderOut, FolderUpdate
from app.services.names import clean_name
from app.services.notes import (
    MAX_FOLDER_DEPTH,
    depth_of,
    folder_parents,
    is_descendant,
    own_folder,
    save_changes,
    subtree_height,
    too_deep,
)

router = APIRouter(prefix="/folders", tags=["folders"])

NAME_TAKEN = "同一位置已有同名文件夹"


@router.get("", response_model=list[FolderOut])
async def list_folders(user: CurrentUser, session: Session) -> list[Folder]:
    rows = await session.scalars(
        select(Folder).where(Folder.user_id == user.id).order_by(Folder.name)
    )
    return list(rows)


@router.post("", response_model=FolderOut)
async def create_folder(body: FolderCreate, user: CurrentUser, session: Session) -> Folder:
    name = clean_name(body.name, "文件夹名")
    if body.parent_id is not None:
        await own_folder(session, user.id, body.parent_id)
        if depth_of(await folder_parents(session, user.id), body.parent_id) >= MAX_FOLDER_DEPTH:
            raise too_deep()
    folder = Folder(user_id=user.id, parent_id=body.parent_id, name=name)
    session.add(folder)
    await save_changes(session, user.id, NAME_TAKEN)
    return folder


@router.patch("/{folder_id}", response_model=FolderOut)
async def update_folder(
    folder_id: int, body: FolderUpdate, user: CurrentUser, session: Session
) -> Folder:
    """重命名和 / 或移动。parentId 传 null 表示移到根目录。"""
    folder = await own_folder(session, user.id, folder_id)
    if body.name is not None:
        folder.name = clean_name(body.name, "文件夹名")
    if "parent_id" in body.model_fields_set and body.parent_id != folder.parent_id:
        parent_id = body.parent_id
        if parent_id is not None:
            await own_folder(session, user.id, parent_id)
            parents = await folder_parents(session, user.id)
            if is_descendant(parents, parent_id, folder.id):
                raise AppError(400, "invalid_move", "不能移动到自身或其子文件夹中")
            if depth_of(parents, parent_id) + subtree_height(parents, folder.id) > MAX_FOLDER_DEPTH:
                raise too_deep()
        folder.parent_id = parent_id
    await save_changes(session, user.id, NAME_TAKEN)
    await session.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(folder_id: int, user: CurrentUser, session: Session) -> None:
    folder = await own_folder(session, user.id, folder_id)
    await session.delete(folder)  # 子文件夹和笔记由数据库外键级联删除
    await save_changes(session, user.id, NAME_TAKEN)
