import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.core.security import check_scope
from app.core.database import get_connection

router = APIRouter(prefix="/folders", tags=["Folders"])
MAX_FAVORITES = 3  # favourite folders are shown as tabs in the Document Hub


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    parent_id: Optional[str] = Field(None, description="Folder to create it in; empty for the top level")


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120, description="New name")
    parent_id: Optional[str] = Field(None, description="Move into this folder")
    move_to_top: bool = Field(False, description="Move to the top level (parent_id is ignored)")
    favorite: Optional[bool] = Field(None, description=f"Pin as a favourite (at most {MAX_FAVORITES}) or unpin")


class FolderResponse(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    created_at: str
    document_count: int = 0
    folder_count: int = 0
    favorite: bool = False
    favorite_rank: Optional[int] = None


def _clean(name: str) -> str:
    name = " ".join(name.replace("/", "-").replace("\\", "-").split())
    if not name:
        raise HTTPException(status_code=400, detail="A folder needs a name.")
    return name[:120]


def owned_folder(conn, folder_id: Optional[str], owner_id: str) -> Optional[dict]:
    """The caller's folder, or 404 exactly like a missing one (other people's folders are not revealed)."""
    if not folder_id:
        return None
    row = conn.execute("SELECT * FROM folders WHERE id = ? AND owner_id = ?", (folder_id, owner_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Folder not found")
    return dict(row)


def _name_taken(conn, owner_id: str, parent_id: Optional[str], name: str, except_id: Optional[str] = None) -> bool:
    sql = "SELECT id, name FROM folders WHERE owner_id = ? AND " + ("parent_id = ?" if parent_id else "parent_id IS NULL")
    params = [owner_id] + ([parent_id] if parent_id else [])
    return any(r["name"].lower() == name.lower() and r["id"] != except_id for r in conn.execute(sql, params).fetchall())


def _list(conn, owner_id: str) -> List[dict]:
    folders = [dict(r) for r in conn.execute(
        "SELECT id, name, parent_id, created_at, favorite_rank FROM folders WHERE owner_id = ? ORDER BY name", (owner_id,)).fetchall()]
    docs = {}
    for r in conn.execute("SELECT folder_id, COUNT(*) AS n FROM documents WHERE owner_id = ? AND folder_id IS NOT NULL GROUP BY folder_id",
                          (owner_id,)).fetchall():
        docs[r["folder_id"]] = int(r["n"])
    subs = {}
    for f in folders:
        if f["parent_id"]:
            subs[f["parent_id"]] = subs.get(f["parent_id"], 0) + 1
    for f in folders:
        f["document_count"] = docs.get(f["id"], 0)
        f["folder_count"] = subs.get(f["id"], 0)
        f["favorite"] = f["favorite_rank"] is not None
    return sorted(folders, key=lambda f: f["name"].lower())


@router.get("", response_model=List[FolderResponse])
def list_folders(auth: dict = Depends(check_scope("doc:read"))):
    """Every folder of the caller (the whole tree; parent_id links them), with how many documents and subfolders each holds."""
    conn = get_connection()
    try:
        return _list(conn, auth["user_id"])
    finally:
        conn.close()


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
def create_folder(payload: FolderCreate, auth: dict = Depends(check_scope("doc:write"))):
    """Creates a folder at the top level or inside another of the caller's folders. Names are unique within a folder."""
    name = _clean(payload.name)
    conn = get_connection()
    try:
        owned_folder(conn, payload.parent_id, auth["user_id"])
        if _name_taken(conn, auth["user_id"], payload.parent_id, name):
            raise HTTPException(status_code=409, detail=f'A folder named "{name}" already exists here.')
        folder_id = f"fld_{uuid.uuid4().hex[:12]}"
        created = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO folders (id, name, parent_id, owner_id, created_at) VALUES (?, ?, ?, ?, ?)",
                     (folder_id, name, payload.parent_id or None, auth["user_id"], created))
        conn.commit()
        return {"id": folder_id, "name": name, "parent_id": payload.parent_id or None, "created_at": created}
    finally:
        conn.close()


@router.patch("/{folder_id}", response_model=FolderResponse)
def update_folder(folder_id: str, payload: FolderUpdate, auth: dict = Depends(check_scope("doc:write"))):
    """
    Renames a folder, moves it into another folder (or to the top level with move_to_top), and/or pins it as
    a favourite (favorite: true, at most 3, shown as tabs in the Document Hub) or unpins it (favorite: false).
    """
    conn = get_connection()
    try:
        folder = owned_folder(conn, folder_id, auth["user_id"])
        name = _clean(payload.name) if payload.name is not None else folder["name"]
        parent = folder["parent_id"]
        if payload.move_to_top:
            parent = None
        elif payload.parent_id:
            owned_folder(conn, payload.parent_id, auth["user_id"])
            # A folder cannot go inside itself or one of its own subfolders
            p = payload.parent_id
            while p:
                if p == folder_id:
                    raise HTTPException(status_code=400, detail="A folder cannot be moved into itself or its own subfolder.")
                row = conn.execute("SELECT parent_id FROM folders WHERE id = ?", (p,)).fetchone()
                p = row["parent_id"] if row else None
            parent = payload.parent_id
        if _name_taken(conn, auth["user_id"], parent, name, except_id=folder_id):
            raise HTTPException(status_code=409, detail=f'A folder named "{name}" already exists there.')
        conn.execute("UPDATE folders SET name = ?, parent_id = ? WHERE id = ?", (name, parent, folder_id))
        if payload.favorite is True and folder.get("favorite_rank") is None:
            ranks = [r["favorite_rank"] for r in conn.execute(
                "SELECT favorite_rank FROM folders WHERE owner_id = ? AND favorite_rank IS NOT NULL", (auth["user_id"],)).fetchall()]
            if len(ranks) >= MAX_FAVORITES:
                raise HTTPException(status_code=409, detail=f"You can pin up to {MAX_FAVORITES} favourite folders. Unpin one first.")
            conn.execute("UPDATE folders SET favorite_rank = ? WHERE id = ?", (max(ranks, default=0) + 1, folder_id))
        elif payload.favorite is False:
            conn.execute("UPDATE folders SET favorite_rank = NULL WHERE id = ?", (folder_id,))
        conn.commit()
        return next(f for f in _list(conn, auth["user_id"]) if f["id"] == folder_id)
    finally:
        conn.close()


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: str, auth: dict = Depends(check_scope("doc:write"))):
    """
    Deletes a folder. Nothing inside is deleted: its documents and subfolders move up into the
    folder that contained it (or to the top level).
    """
    conn = get_connection()
    try:
        folder = owned_folder(conn, folder_id, auth["user_id"])
        parent = folder["parent_id"]
        conn.execute("UPDATE documents SET folder_id = ? WHERE folder_id = ? AND owner_id = ?", (parent, folder_id, auth["user_id"]))
        # Subfolders keep their names; one that clashes with a folder already there gets a number
        for sub in conn.execute("SELECT id, name FROM folders WHERE parent_id = ? AND owner_id = ?",
                                (folder_id, auth["user_id"])).fetchall():
            name, n = sub["name"], 2
            while _name_taken(conn, auth["user_id"], parent, name, except_id=sub["id"]) or name.lower() == folder["name"].lower():
                name, n = f'{sub["name"]} {n}', n + 1
            conn.execute("UPDATE folders SET parent_id = ?, name = ? WHERE id = ?", (parent, name, sub["id"]))
        conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        conn.commit()
    finally:
        conn.close()
