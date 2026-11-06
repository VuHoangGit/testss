"""Endpoints thư mục: list / tạo / xóa (chỉ xóa khi trống)."""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.document import Document
from app.models.folder import Folder
from app.schemas.documents import FolderCreate, FolderOut

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("", response_model=list[FolderOut])
def list_folders(db: DbSession, current: CurrentUser) -> list[FolderOut]:
    user = current
    rows = db.execute(
        select(Folder, func.count(Document.id).label("document_count"))
        .outerjoin(Document, Document.folder_id == Folder.id)
        .where(Folder.owner_id == user.id)
        .group_by(Folder.id)
        .order_by(Folder.name)
    ).all()
    return [FolderOut(id=f.id, name=f.name, document_count=int(count)) for f, count in rows]


@router.post("", response_model=FolderOut, status_code=201)
def create_folder(body: FolderCreate, db: DbSession, current: CurrentUser) -> FolderOut:
    user = current
    folder = Folder(owner_id=user.id, name=body.name.strip())
    db.add(folder)
    db.commit()
    return FolderOut(id=folder.id, name=folder.name, document_count=0)


@router.delete("/{folder_id}")
def delete_folder(
    folder_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> dict[str, str]:
    user = current
    folder = db.get(Folder, folder_id)
    if folder is None or folder.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Folder not found")
    count = db.scalar(
        select(func.count()).select_from(Document).where(Document.folder_id == folder.id)
    )
    if (count or 0) > 0:
        raise HTTPException(status_code=409, detail="Folder still contains documents and cannot be deleted")
    db.delete(folder)
    db.commit()
    return {"detail": "Folder deleted"}
