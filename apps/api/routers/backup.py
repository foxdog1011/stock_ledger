"""Database backup and restore endpoints."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()

_SQLITE_MAGIC = b"SQLite format 3\x00"


@router.get("/backup/db", summary="Download the SQLite database file")
def backup_db(ledger: StockLedger = Depends(get_ledger)):
    """Stream the raw SQLite file as ``ledger.db``."""
    db_path: Path = ledger.db_path
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database file not found")
    return FileResponse(
        path=str(db_path),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=ledger.db"},
    )


@router.post("/restore/db", summary="Upload and restore the SQLite database")
async def restore_db(
    file: UploadFile = File(...),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    Replace the current database with the uploaded ``.db`` file.

    The file is validated (SQLite magic bytes) before overwriting.
    The server does **not** need to restart – the next request will use the
    new database because ``StockLedger`` opens a fresh connection per operation.

    **Caution**: this is irreversible.  Download a backup first.
    """
    if file.filename and not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="Uploaded file must have a .db extension")

    content = await file.read()

    max_size = 500 * 1024 * 1024  # 500 MB
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 500 MB.")

    if not content.startswith(_SQLITE_MAGIC):
        raise HTTPException(status_code=400, detail="Not a valid SQLite database file")

    db_path: Path = ledger.db_path
    tmp_path = db_path.with_suffix(".restore_tmp")

    try:
        tmp_path.write_bytes(content)
        shutil.move(str(tmp_path), str(db_path))
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Restore failed: {exc}")

    return {"ok": True, "bytes": len(content), "message": "Database restored successfully."}
