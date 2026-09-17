# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

FILES = [
    ROOT / "app" / "services" / "school_merger_level_batch_service.py",
    ROOT / "app" / "services" / "school_merger_official_registry.py",
    ROOT / "app" / "templates" / "data_tools" / "school_merger_level_batch.html",
    ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json",
    ROOT / "data" / "school_merger_registry" / "qd3805_mn_resolution.json",
]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def db_check():
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA foreign_keys=ON")
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = len(con.execute("PRAGMA foreign_key_check").fetchall())
        return integrity, fk
    finally:
        con.close()

print("=" * 118)
print("THU THẬP NỀN HIỆN TẠI - MẦM NON QĐ3805")
print("Chế độ: CHỈ ĐỌC / KHÔNG SỬA MÃ NGUỒN / KHÔNG GHI DATABASE")
print("=" * 118)

if not ROOT.exists():
    raise SystemExit("Không tìm thấy C:\\PhoCap")
if not DB.exists():
    raise SystemExit("Không tìm thấy phocap.db")

integrity, fk = db_check()
if integrity.lower() != "ok" or fk:
    raise SystemExit(f"Database không đạt kiểm tra: integrity={integrity}, fk={fk}")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
export_dir = ROOT / "exports" / f"Thu_Thap_Nen_MN_QD3805_{stamp}"
export_dir.mkdir(parents=True, exist_ok=False)

manifest = {
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "database": str(DB),
    "database_integrity": integrity,
    "foreign_key_errors": fk,
    "files": [],
}

for src in FILES:
    item = {
        "path": str(src),
        "exists": src.exists(),
    }
    if src.exists():
        rel_name = src.name
        dst = export_dir / rel_name
        shutil.copy2(src, dst)
        item["sha256"] = sha256(src)
        item["size"] = src.stat().st_size
        item["copied_as"] = str(dst)
    manifest["files"].append(item)

manifest_path = export_dir / "MANIFEST.json"
manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

zip_out = ROOT / "exports" / f"nen_hien_tai_MN_QD3805_{stamp}.zip"
with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in export_dir.iterdir():
        if p.is_file():
            z.write(p, p.name)

print("Integrity:", integrity)
print("Foreign key errors:", fk)
print("-" * 118)
for item in manifest["files"]:
    if item["exists"]:
        print(item["path"])
        print("  SHA256:", item["sha256"])
    else:
        print(item["path"])
        print("  KHÔNG TỒN TẠI")
print("-" * 118)
print("ĐÃ TẠO ZIP:", zip_out)
print("Database: KHÔNG THAY ĐỔI")
print("=" * 118)
