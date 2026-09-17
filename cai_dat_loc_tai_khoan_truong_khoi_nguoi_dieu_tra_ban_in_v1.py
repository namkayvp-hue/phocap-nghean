# -*- coding: utf-8 -*-
from __future__ import annotations
import ast, hashlib, os, shutil, sqlite3, subprocess, sys, traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
TARGET = PROJECT / "app" / "routers" / "survey_print.py"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_loc_tai_khoan_truong_khoi_ban_in_{STAMP}"
REPORT = EXPORTS / f"bao_cao_loc_tai_khoan_truong_khoi_ban_in_{STAMP}.txt"

MARK_HELPER = "# === LOC_TAI_KHOAN_TRUONG_KHOI_NGUOI_DIEU_TRA_V1_HELPER ==="
MARK_CALL = "# === LOC_TAI_KHOAN_TRUONG_KHOI_NGUOI_DIEU_TRA_V1_CALL ==="

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")

def db_health():
    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        con.execute("PRAGMA query_only = ON")
        return (
            con.execute("PRAGMA integrity_check").fetchone()[0],
            len(con.execute("PRAGMA foreign_key_check").fetchall()),
        )
    finally:
        con.close()

def patch(src: str) -> str:
    if MARK_HELPER not in src:
        anchor = '@router.get(\n    "/{batch_id}/phieu-in-thuc-dia",'
        pos = src.find(anchor)
        if pos < 0:
            raise RuntimeError("Không tìm thấy route phieu-in-thuc-dia.")

        helper = f'''
{MARK_HELPER}
def la_tai_khoan_don_vi_truong(user) -> bool:
    if user is None:
        return False

    username = str(getattr(user, "username", "") or "").strip().lower()

    # CBQL vẫn là người điều tra hợp lệ khi được phân công.
    if username.startswith("cbql."):
        return False

    role = getattr(user, "role", None)
    role_code = str(getattr(role, "code", "") or "").strip().upper()

    if role_code:
        return role_code == "TRUONG"

    # Tương thích tài khoản đơn vị trường cũ.
    return username.startswith("truong_")


'''
        src = src[:pos] + helper + src[pos:]

    if MARK_CALL not in src:
        old = '''        investigator_names = [
            item.user.full_name
            for item in sorted(
                survey_form.investigators,
                key=lambda item: item.order_number,
            )
            if item.user is not None
        ]
'''
        new = f'''        {MARK_CALL}
        investigator_names = [
            item.user.full_name
            for item in sorted(
                survey_form.investigators,
                key=lambda item: item.order_number,
            )
            if (
                item.user is not None
                and not la_tai_khoan_don_vi_truong(item.user)
            )
        ]
'''
        count = src.count(old)
        if count != 1:
            raise RuntimeError(
                f"Không tìm thấy đúng block investigator_names; count={count}"
            )
        src = src.replace(old, new, 1)

    ast.parse(src)
    for token in (
        MARK_HELPER,
        MARK_CALL,
        "la_tai_khoan_don_vi_truong",
        'role_code == "TRUONG"',
        'username.startswith("truong_")',
        '"investigator_names": investigator_names',
    ):
        if token not in src:
            raise RuntimeError("Thiếu marker/token sau sửa: " + token)
    return src

def main():
    print("=" * 108)
    print("LỌC TÀI KHOẢN ĐƠN VỊ TRƯỜNG KHỎI CỘT NGƯỜI ĐIỀU TRA")
    print("=" * 108)

    if not TARGET.exists() or not DB.exists():
        raise RuntimeError("Thiếu survey_print.py hoặc phocap.db.")

    db_sha_before = sha(DB)
    integrity, fk = db_health()
    if str(integrity).lower() != "ok" or fk != 0:
        raise RuntimeError(f"DB health không đạt: integrity={integrity}, FK={fk}")

    src_before = read(TARGET)
    ast.parse(src_before)
    src_sha_before = sha(TARGET)

    print("[1/6] DB integrity=ok; FK=0.")
    print("[2/6] survey_print.py AST: OK.")

    backup_file = BACKUP / TARGET.relative_to(PROJECT)
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, backup_file)
    print(f"[3/6] Backup: {backup_file}")

    try:
        src_after = patch(src_before)
        TARGET.write_text(src_after, encoding="utf-8")

        subprocess.run(
            [sys.executable, "-m", "py_compile", str(TARGET)],
            cwd=str(PROJECT),
            check=True,
        )
        print("[4/6] Đã lọc tài khoản trường; AST + py_compile: ĐẠT.")

        db_sha_after = sha(DB)
        integrity2, fk2 = db_health()
        if db_sha_after != db_sha_before or integrity2 != integrity or fk2 != fk:
            raise RuntimeError("Database thay đổi bất thường.")

        print("[5/6] Database: KHÔNG THAY ĐỔI.")

        EXPORTS.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            "\n".join([
                "SỬA BẢN IN NGƯỜI ĐIỀU TRA",
                f"Source trước: {src_sha_before}",
                f"Source sau: {sha(TARGET)}",
                f"DB trước: {db_sha_before}",
                f"DB sau: {db_sha_after}",
                "Đã loại tài khoản đơn vị trường khỏi investigator_names.",
                "Giữ giáo viên và CBQL thực sự.",
                "Database: KHÔNG THAY ĐỔI.",
            ]),
            encoding="utf-8-sig",
        )
        print(f"[6/6] Báo cáo: {REPORT}")
        print("CÀI ĐẶT THÀNH CÔNG.")
        return 0

    except Exception:
        shutil.copy2(backup_file, TARGET)
        print("Đã rollback survey_print.py.")
        raise

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("[LỖI]", exc)
        traceback.print_exc()
        raise SystemExit(1)
