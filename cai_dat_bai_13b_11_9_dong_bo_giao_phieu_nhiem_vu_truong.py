from __future__ import annotations

import ast
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
SURVEYS = APP / "routers" / "surveys.py"
DB_PATH = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = PROJECT / "exports" / f"backup_bai_13b_11_9_{STAMP}"
SOURCE_BACKUP = BACKUP_DIR / "source" / "app" / "routers" / "surveys.py"
DB_BACKUP = BACKUP_DIR / "database" / "phocap.db"

MARK_HELPER_START = "# === BAI_13B_11_9_SYNC_SCHOOL_ASSIGNMENT_START ==="
MARK_HELPER_END = "# === BAI_13B_11_9_SYNC_SCHOOL_ASSIGNMENT_END ==="
MARK_ROUTE_START = "# === BAI_13B_11_9_ROUTE_SYNC_START ==="
MARK_ROUTE_END = "# === BAI_13B_11_9_ROUTE_SYNC_END ==="

HELPER_CODE = '# === BAI_13B_11_9_SYNC_SCHOOL_ASSIGNMENT_START ===\ndef dong_bo_nhiem_vu_truong_tu_phieu_da_giao(\n    *,\n    db: Session,\n    batch_id: int,\n    actor_user_id: int | None = None,\n) -> int:\n    batch = db.get(SurveyBatch, int(batch_id))\n    if batch is None:\n        return 0\n\n    school_ids = db.scalars(\n        select(User.school_id)\n        .select_from(SurveyFormInvestigator)\n        .join(User, User.id == SurveyFormInvestigator.user_id)\n        .join(SurveyForm, SurveyForm.id == SurveyFormInvestigator.survey_form_id)\n        .where(\n            SurveyForm.survey_batch_id == int(batch_id),\n            User.school_id.is_not(None),\n        )\n        .distinct()\n    ).all()\n\n    created = 0\n    for raw_school_id in school_ids:\n        if raw_school_id is None:\n            continue\n\n        try:\n            school_id = int(raw_school_id)\n        except (TypeError, ValueError):\n            continue\n\n        school = db.get(School, school_id)\n        if school is None or school.commune_id != batch.commune_id:\n            continue\n\n        existing_id = db.scalar(\n            select(SurveySchoolAssignment.id).where(\n                SurveySchoolAssignment.survey_batch_id == int(batch_id),\n                SurveySchoolAssignment.school_id == school_id,\n            )\n        )\n        if existing_id is not None:\n            continue\n\n        kwargs: dict[str, object] = {\n            "survey_batch_id": int(batch_id),\n            "school_id": school_id,\n        }\n\n        table = SurveySchoolAssignment.__table__\n\n        if "assigned_by_user_id" in table.c:\n            actor_id = actor_user_id\n            if actor_id is None:\n                actor_id = db.scalar(\n                    select(User.id)\n                    .where(\n                        User.commune_id == batch.commune_id,\n                        User.role.has(code="XA"),\n                    )\n                    .order_by(User.id.asc())\n                )\n            if actor_id is not None:\n                kwargs["assigned_by_user_id"] = int(actor_id)\n\n        if "notes" in table.c:\n            kwargs["notes"] = (\n                "Đồng bộ tự động từ dữ liệu phiếu đã giao - Bài 13B-11.9."\n            )\n\n        missing_required: list[str] = []\n        for column in table.columns:\n            if column.primary_key:\n                continue\n            if column.name in kwargs:\n                continue\n            if column.nullable:\n                continue\n            if column.default is not None:\n                continue\n            if column.server_default is not None:\n                continue\n            missing_required.append(column.name)\n\n        if missing_required:\n            raise RuntimeError(\n                "Không thể tự đồng bộ nhiệm vụ trường vì model "\n                "SurveySchoolAssignment có cột bắt buộc chưa xác định default: "\n                + ", ".join(missing_required)\n            )\n\n        db.add(SurveySchoolAssignment(**kwargs))\n        created += 1\n\n    if created:\n        db.flush()\n\n    return created\n# === BAI_13B_11_9_SYNC_SCHOOL_ASSIGNMENT_END ===\n'
NEW_ROUTE_BODY = '    # === BAI_13B_11_9_ROUTE_SYNC_START ===\n    response = await luu_phan_cong_v4_theo_cap(\n        batch_id=batch_id,\n        assignment_level="school",\n        request=request,\n        db=db,\n    )\n\n    try:\n        auth_user = request.scope.get("auth_user") or {}\n        actor_user_id = auth_user.get("id")\n        created = dong_bo_nhiem_vu_truong_tu_phieu_da_giao(\n            db=db,\n            batch_id=batch_id,\n            actor_user_id=actor_user_id,\n        )\n        if created:\n            db.commit()\n    except Exception:\n        db.rollback()\n\n    return response\n    # === BAI_13B_11_9_ROUTE_SYNC_END ===\n'
BACKFILL_CODE = 'from sqlalchemy import select\nfrom app.database import get_db\nfrom app.models import SurveyForm\nfrom app.routers.surveys import dong_bo_nhiem_vu_truong_tu_phieu_da_giao\n\ngen = get_db()\ndb = next(gen)\ntry:\n    batch_ids = list(\n        db.scalars(\n            select(SurveyForm.survey_batch_id)\n            .where(SurveyForm.survey_batch_id.is_not(None))\n            .distinct()\n            .order_by(SurveyForm.survey_batch_id.asc())\n        ).all()\n    )\n\n    created_total = 0\n    for batch_id in batch_ids:\n        created_total += dong_bo_nhiem_vu_truong_tu_phieu_da_giao(\n            db=db,\n            batch_id=int(batch_id),\n            actor_user_id=None,\n        )\n\n    db.commit()\n    print(f"BACKFILL_BATCHES={len(batch_ids)}")\n    print(f"BACKFILL_CREATED={created_total}")\nfinally:\n    try:\n        gen.close()\n    except Exception:\n        pass\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def sqlite_backup(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_con = sqlite3.connect(str(src))
    dst_con = sqlite3.connect(str(dst))
    try:
        src_con.backup(dst_con)
    finally:
        dst_con.close()
        src_con.close()


def restore_db() -> None:
    if not DB_BACKUP.exists():
        return
    src_con = sqlite3.connect(str(DB_BACKUP))
    dst_con = sqlite3.connect(str(DB_PATH))
    try:
        src_con.backup(dst_con)
    finally:
        dst_con.close()
        src_con.close()


def backup_all() -> None:
    SOURCE_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SURVEYS, SOURCE_BACKUP)
    sqlite_backup(DB_PATH, DB_BACKUP)


def restore_source() -> None:
    if SOURCE_BACKUP.exists():
        shutil.copy2(SOURCE_BACKUP, SURVEYS)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def get_db_health(path: Path) -> tuple[str, int]:
    con = sqlite3.connect(str(path))
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
        return str(integrity), int(fk_count)
    finally:
        con.close()


def count_assignments(path: Path) -> int:
    con = sqlite3.connect(str(path))
    try:
        return int(
            con.execute(
                "SELECT COUNT(*) FROM survey_school_assignments"
            ).fetchone()[0]
            or 0
        )
    finally:
        con.close()


def ensure_model_import(text: str) -> str:
    if "SurveySchoolAssignment," in text:
        return text

    anchor = "    SurveyFormInvestigator,\n"
    if anchor not in text:
        raise RuntimeError(
            "Không tìm thấy vị trí import SurveyFormInvestigator."
        )

    return text.replace(
        anchor,
        "    SurveyFormInvestigator,\n"
        "    SurveySchoolAssignment,  # BAI_13B_11_9_IMPORT\n",
        1,
    )


def insert_helper(text: str) -> str:
    if MARK_HELPER_START in text:
        return text

    anchor = "def dieu_kien_phieu_da_giao_nhan_su_truong("
    idx = text.find(anchor)
    if idx < 0:
        raise RuntimeError(
            "Không tìm thấy hàm dieu_kien_phieu_da_giao_nhan_su_truong."
        )

    return text[:idx] + HELPER_CODE + "\n\n" + text[idx:]


def source_segment(node: ast.AST, text: str) -> str:
    return ast.get_source_segment(text, node) or ""


def patch_school_route(text: str) -> str:
    if MARK_ROUTE_START in text:
        return text

    tree = ast.parse(text)
    target = None

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "luu_giao_phieu_cho_truong":
                target = node
                break

    if target is None:
        raise RuntimeError("Không tìm thấy hàm luu_giao_phieu_cho_truong.")
    if not isinstance(target, ast.AsyncFunctionDef):
        raise RuntimeError("luu_giao_phieu_cho_truong không phải async.")

    body_text = "\n".join(
        source_segment(stmt, text) for stmt in target.body
    )
    if "luu_phan_cong_v4_theo_cap" not in body_text:
        raise RuntimeError(
            "Cấu trúc hàm giao phiếu cho trường khác dự kiến."
        )

    lines = text.splitlines(keepends=True)
    start = target.body[0].lineno - 1
    end = target.body[-1].end_lineno

    return (
        "".join(lines[:start])
        + NEW_ROUTE_BODY
        + "".join(lines[end:])
    )


def patch_source() -> None:
    text = read_text(SURVEYS)
    text = ensure_model_import(text)
    text = insert_helper(text)
    text = patch_school_route(text)
    write_text(SURVEYS, text)


def verify_source() -> None:
    text = read_text(SURVEYS)

    for marker in (
        "SurveySchoolAssignment,",
        MARK_HELPER_START,
        MARK_HELPER_END,
        MARK_ROUTE_START,
        MARK_ROUTE_END,
        "dong_bo_nhiem_vu_truong_tu_phieu_da_giao",
    ):
        if marker not in text:
            raise RuntimeError(f"Thiếu marker sau cài: {marker}")

    ast.parse(text)

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(SURVEYS)],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if result.returncode != 0:
        raise RuntimeError("py_compile surveys.py không đạt.")


def run_backfill() -> tuple[int, int]:
    result = subprocess.run(
        [sys.executable, "-c", BACKFILL_CODE],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if result.returncode != 0:
        raise RuntimeError("Đồng bộ dữ liệu hiện có không thành công.")

    batches = 0
    created = 0

    for line in result.stdout.splitlines():
        if line.startswith("BACKFILL_BATCHES="):
            batches = int(line.split("=", 1)[1])
        elif line.startswith("BACKFILL_CREATED="):
            created = int(line.split("=", 1)[1])

    return batches, created


def main() -> int:
    print("=" * 112)
    print("BÀI 13B-11.9 - ĐỒNG BỘ GIAO PHIẾU <-> NHIỆM VỤ TRƯỜNG")
    print("=" * 112)
    print()
    print("MỤC TIÊU:")
    print(" - Trường đã có phiếu thì không còn báo xã chưa giao nhiệm vụ.")
    print(" - Các lần Xã giao phiếu sau tự đồng bộ nhiệm vụ trường.")
    print(" - Không xóa phiếu, không đổi người điều tra.")
    print()
    print("AN TOÀN:")
    print(" - Backup surveys.py.")
    print(" - Backup database bằng SQLite Backup API.")
    print(" - Chỉ tạo survey_school_assignments còn thiếu.")
    print(" - Không ghi đè nhiệm vụ trường đã có.")
    print()

    if not SURVEYS.exists():
        raise RuntimeError(f"Không tìm thấy: {SURVEYS}")
    if not DB_PATH.exists():
        raise RuntimeError(f"Không tìm thấy database: {DB_PATH}")

    integrity_before, fk_before = get_db_health(DB_PATH)
    if integrity_before.lower() != "ok" or fk_before != 0:
        raise RuntimeError(
            f"Database chưa an toàn: integrity={integrity_before}, "
            f"foreign_key_errors={fk_before}"
        )

    before_count = count_assignments(DB_PATH)

    BACKUP_DIR.mkdir(parents=True, exist_ok=False)
    backup_all()
    print("Backup:", BACKUP_DIR)
    print("survey_school_assignments trước cài:", before_count)

    db_touched = False

    try:
        patch_source()
        verify_source()

        db_touched = True
        batches, created = run_backfill()

        integrity_after, fk_after = get_db_health(DB_PATH)
        if integrity_after.lower() != "ok":
            raise RuntimeError(
                f"integrity_check sau cài không đạt: {integrity_after}"
            )
        if fk_after != 0:
            raise RuntimeError(
                f"foreign_key_check sau cài có {fk_after} lỗi."
            )

        after_count = count_assignments(DB_PATH)

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - surveys.py AST / py_compile: OK")
        print(f" - Số đợt có phiếu được rà: {batches}")
        print(f" - Nhiệm vụ trường bổ sung: {created}")
        print(
            f" - survey_school_assignments: "
            f"{before_count} -> {after_count}"
        )
        print(" - integrity_check: OK")
        print(" - foreign_key_check: 0 lỗi")
        print(" - Phiếu / người điều tra: KHÔNG BỊ XÓA HAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.9 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore_source()
        clear_cache()

        if db_touched:
            restore_db()

        print("ĐÃ KHÔI PHỤC SOURCE VÀ DATABASE.")
        print("Backup:", BACKUP_DIR)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
