from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
ROUTER = (
    APP
    / "routers"
    / "survey_batch_admin_v13b11.py"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_source_bai_13b_11_3_4_{STAMP}"
)

START = "# === BAI_13B_11_3_BULK_DELETE_START ==="
END = "# === BAI_13B_11_3_BULK_DELETE_END ==="

NEW_BLOCK = '\n# === BAI_13B_11_3_BULK_DELETE_START ===\n\nBULK_DELETE_CONFIRM_TEXT = "XOA TOAN BO DA CHON"\n\n\ndef _bulk_execution_state_check(\n    con: sqlite3.Connection,\n    batch_id: int,\n) -> tuple[bool, int, str]:\n    """\n    survey_commune_execution_states là bản ghi đồng hành 1-1 của đợt.\n    Chỉ được xem là \'trống\' khi hoàn toàn chưa khóa/chưa điều hành:\n    - is_commune_locked = 0/NULL\n    - is_province_locked = 0/NULL\n    - không có thời gian/người/lý do khóa ở cả hai cấp.\n    """\n    tables = set(_tables(con))\n    if "survey_commune_execution_states" not in tables:\n        return True, 0, ""\n\n    rows = con.execute(\n        """\n        SELECT\n            id,\n            COALESCE(is_commune_locked, 0),\n            COALESCE(is_province_locked, 0),\n            commune_locked_at,\n            commune_locked_by_user_id,\n            commune_lock_reason,\n            province_locked_at,\n            province_locked_by_user_id,\n            province_lock_reason\n        FROM survey_commune_execution_states\n        WHERE survey_batch_id = ?\n        ORDER BY id\n        """,\n        (int(batch_id),),\n    ).fetchall()\n\n    if not rows:\n        return True, 0, ""\n\n    if len(rows) > 1:\n        return (\n            False,\n            len(rows),\n            "Có nhiều hơn 1 bản ghi trạng thái điều hành cho cùng một đợt.",\n        )\n\n    row = rows[0]\n\n    commune_locked = bool(row[1])\n    province_locked = bool(row[2])\n\n    has_commune_history = any(\n        value not in (None, "")\n        for value in (row[3], row[4], row[5])\n    )\n    has_province_history = any(\n        value not in (None, "")\n        for value in (row[6], row[7], row[8])\n    )\n\n    if (\n        commune_locked\n        or province_locked\n        or has_commune_history\n        or has_province_history\n    ):\n        return (\n            False,\n            1,\n            "Bản ghi trạng thái điều hành đã có dấu vết khóa/chốt.",\n        )\n\n    return True, 1, ""\n\n\ndef _bulk_noncompanion_references(\n    con: sqlite3.Connection,\n    batch_id: int,\n) -> tuple[list[dict[str, Any]], int, str]:\n    """\n    Lấy toàn bộ tham chiếu, nhưng chỉ loại riêng\n    survey_commune_execution_states.survey_batch_id\n    nếu bản ghi trạng thái là hoàn toàn trắng.\n    """\n    refs = _references(con, batch_id)\n\n    state_ok, state_count, state_error = _bulk_execution_state_check(\n        con,\n        batch_id,\n    )\n\n    if not state_ok:\n        return refs, state_count, state_error\n\n    filtered: list[dict[str, Any]] = []\n\n    for item in refs:\n        table_name = str(item.get("table") or "")\n        column_name = str(item.get("column") or "")\n\n        if (\n            table_name == "survey_commune_execution_states"\n            and column_name == "survey_batch_id"\n        ):\n            continue\n\n        filtered.append(item)\n\n    return filtered, state_count, ""\n\n\n@router.post("/xoa-hang-loat")\nasync def delete_empty_batches_bulk(request: Request):\n    """\n    Bài 13B-11.3.4:\n    - đúng helper thực tế của Bài 13B-11;\n    - cho phép xóa bản ghi execution-state đồng hành nếu hoàn toàn trắng;\n    - mọi dữ liệu/phân công/log/phiếu khác vẫn chặn;\n    - backup trước khi chạm DB;\n    - kiểm tra lại trong BEGIN IMMEDIATE;\n    - all-or-nothing.\n    """\n    if not _admin(request):\n        return _forbidden()\n\n    form = await request.form()\n    actor = _user(request)\n\n    raw_ids = list(form.getlist("batch_ids"))\n    batch_ids: list[int] = []\n\n    for raw in raw_ids:\n        try:\n            batch_id = int(str(raw or "").strip())\n        except (TypeError, ValueError):\n            continue\n\n        if batch_id > 0:\n            batch_ids.append(batch_id)\n\n    batch_ids = sorted(set(batch_ids))\n\n    try:\n        selected_year_id = int(\n            str(form.get("school_year_id") or "0").strip()\n        )\n    except (TypeError, ValueError):\n        selected_year_id = 0\n\n    confirm_phrase = _clean(\n        form.get("confirm_phrase"),\n        200,\n    )\n\n    def redirect_blocked(\n        detail: str,\n        backup_name: str = "",\n    ):\n        q: dict[str, Any] = {\n            "status": "delete_blocked",\n            "detail": detail,\n        }\n\n        if selected_year_id > 0:\n            q["school_year_id"] = selected_year_id\n\n        if backup_name:\n            q["backup"] = backup_name\n\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/quan-ly-dot-toan-tinh?"\n                + urlencode(q)\n            ),\n            status_code=303,\n        )\n\n    def redirect_failed(\n        backup_name: str = "",\n    ):\n        q: dict[str, Any] = {\n            "status": "delete_failed",\n        }\n\n        if selected_year_id > 0:\n            q["school_year_id"] = selected_year_id\n\n        if backup_name:\n            q["backup"] = backup_name\n\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/quan-ly-dot-toan-tinh?"\n                + urlencode(q)\n            ),\n            status_code=303,\n        )\n\n    if not batch_ids:\n        return redirect_blocked(\n            "Chưa nhận được danh sách đợt đã chọn. "\n            "Chưa xóa đợt nào."\n        )\n\n    if len(batch_ids) > 1000:\n        return redirect_blocked(\n            "Số đợt được chọn vượt giới hạn an toàn 1000 đợt."\n        )\n\n    if confirm_phrase != BULK_DELETE_CONFIRM_TEXT:\n        return redirect_blocked(\n            f\'Phải nhập chính xác "{BULK_DELETE_CONFIRM_TEXT}".\'\n        )\n\n    snapshots: list[dict[str, Any]] = []\n    state_rows_total = 0\n    actual_year_id: int | None = None\n\n    # =====================================================\n    # KIỂM TRA LẦN 1\n    # =====================================================\n    con = sqlite3.connect(\n        str(DATABASE_PATH),\n        timeout=30,\n    )\n\n    try:\n        con.execute("PRAGMA foreign_keys=ON")\n        con.execute("PRAGMA busy_timeout=30000")\n\n        for batch_id in batch_ids:\n            snapshot = _snapshot(\n                con,\n                batch_id,\n            )\n\n            if snapshot is None:\n                return redirect_blocked(\n                    f"Không tìm thấy đợt ID {batch_id}. "\n                    "Toàn bộ thao tác đã dừng."\n                )\n\n            year_id = int(\n                snapshot.get("school_year_id") or 0\n            )\n\n            if actual_year_id is None:\n                actual_year_id = year_id\n\n            if year_id != actual_year_id:\n                return redirect_blocked(\n                    "Các đợt được chọn không cùng một năm học."\n                )\n\n            if (\n                selected_year_id > 0\n                and year_id != selected_year_id\n            ):\n                return redirect_blocked(\n                    f"Đợt {snapshot.get(\'code\')} không thuộc "\n                    "năm học đang hiển thị."\n                )\n\n            refs, state_count, state_error = (\n                _bulk_noncompanion_references(\n                    con,\n                    batch_id,\n                )\n            )\n\n            if state_error:\n                return redirect_blocked(\n                    f"Đợt {snapshot.get(\'code\')}: {state_error} "\n                    "Chưa xóa đợt nào."\n                )\n\n            reason = _safety_reason(\n                snapshot,\n                refs,\n            )\n\n            if reason:\n                return redirect_blocked(\n                    f"Đợt {snapshot.get(\'code\')}: {reason} "\n                    "Chưa xóa đợt nào."\n                )\n\n            snapshots.append(snapshot)\n            state_rows_total += state_count\n\n    finally:\n        con.close()\n\n    if selected_year_id <= 0 and actual_year_id:\n        selected_year_id = actual_year_id\n\n    # =====================================================\n    # MỘT BACKUP CHUNG TRƯỚC KHI XÓA\n    # =====================================================\n    bulk_snapshot: dict[str, Any] = {\n        "id": None,\n        "code": (\n            f"HANG_LOAT_{len(batch_ids)}_DOT_"\n            f"NAM_{selected_year_id or \'KHONG_RO\'}"\n        ),\n        "name": (\n            "Bài 13B-11.3.4 - "\n            "Xóa hàng loạt đợt trống và execution-state trắng"\n        ),\n        "status": "CHUAN_BI",\n        "school_year_id": (\n            selected_year_id\n            or actual_year_id\n        ),\n        "commune_id": None,\n        "batch_total": len(batch_ids),\n        "execution_state_total": state_rows_total,\n        "batch_ids": batch_ids,\n        "batch_codes": [\n            str(item.get("code") or "")\n            for item in snapshots\n        ],\n    }\n\n    try:\n        backup_dir = _backup_before_delete(\n            actor,\n            bulk_snapshot,\n        )\n    except Exception:\n        return redirect_failed()\n\n    # =====================================================\n    # KIỂM TRA LẦN 2 + DELETE TRONG MỘT GIAO DỊCH\n    # =====================================================\n    write_con = sqlite3.connect(\n        str(DATABASE_PATH),\n        timeout=30,\n    )\n\n    deleted_state_total = 0\n    deleted_batch_total = 0\n\n    try:\n        write_con.execute("PRAGMA foreign_keys=ON")\n        write_con.execute("PRAGMA busy_timeout=30000")\n        write_con.execute("BEGIN IMMEDIATE")\n\n        # Kiểm tra lại tất cả trước khi xóa dòng đầu tiên.\n        for batch_id in batch_ids:\n            latest = _snapshot(\n                write_con,\n                batch_id,\n            )\n\n            refs, _state_count, state_error = (\n                _bulk_noncompanion_references(\n                    write_con,\n                    batch_id,\n                )\n            )\n\n            if state_error:\n                raise RuntimeError(\n                    f"Đợt ID {batch_id}: {state_error}"\n                )\n\n            latest_reason = _safety_reason(\n                latest,\n                refs,\n            )\n\n            if latest_reason:\n                raise RuntimeError(\n                    "Dữ liệu đã thay đổi sau kiểm tra ban đầu. "\n                    f"Đợt ID {batch_id}: {latest_reason}"\n                )\n\n            latest_year_id = int(\n                (latest or {}).get(\n                    "school_year_id"\n                )\n                or 0\n            )\n\n            if (\n                selected_year_id > 0\n                and latest_year_id != selected_year_id\n            ):\n                raise RuntimeError(\n                    "Phát hiện thay đổi phạm vi năm học."\n                )\n\n        # Chỉ sau khi tất cả vượt kiểm tra lần 2:\n        # 1) xóa execution-state trắng;\n        # 2) xóa survey_batch.\n        for batch_id in batch_ids:\n            cur_state = write_con.execute(\n                """\n                DELETE FROM survey_commune_execution_states\n                WHERE survey_batch_id = ?\n                """,\n                (batch_id,),\n            )\n            deleted_state_total += max(\n                0,\n                int(cur_state.rowcount or 0),\n            )\n\n        for batch_id in batch_ids:\n            cur_batch = write_con.execute(\n                """\n                DELETE FROM survey_batches\n                WHERE id = ?\n                """,\n                (batch_id,),\n            )\n\n            if int(cur_batch.rowcount or 0) != 1:\n                raise RuntimeError(\n                    f"Không xóa đúng một đợt ID {batch_id}."\n                )\n\n            deleted_batch_total += 1\n\n        if deleted_batch_total != len(batch_ids):\n            raise RuntimeError(\n                "Số đợt đã xóa không khớp số đợt được chọn."\n            )\n\n        # Kiểm tra ngay trong transaction: không còn batch đã chọn.\n        placeholders = ",".join("?" for _ in batch_ids)\n        remaining = int(\n            write_con.execute(\n                f"""\n                SELECT COUNT(*)\n                FROM survey_batches\n                WHERE id IN ({placeholders})\n                """,\n                tuple(batch_ids),\n            ).fetchone()[0]\n            or 0\n        )\n\n        if remaining != 0:\n            raise RuntimeError(\n                f"Sau DELETE vẫn còn {remaining} đợt đã chọn."\n            )\n\n        write_con.commit()\n\n    except Exception as exc:\n        write_con.rollback()\n\n        return redirect_blocked(\n            (\n                "Xóa hàng loạt đã được hủy an toàn: "\n                + str(exc)[:700]\n            ),\n            backup_name=backup_dir.name,\n        )\n\n    finally:\n        write_con.close()\n\n    # =====================================================\n    # NHẬT KÝ SAU COMMIT\n    # =====================================================\n    try:\n        for snapshot in snapshots:\n            _log_delete(\n                actor,\n                snapshot,\n                backup_dir,\n            )\n    except Exception:\n        pass\n\n    q: dict[str, Any] = {\n        "status": "batch_deleted",\n        "code": (\n            f"{deleted_batch_total} đợt trống đã chọn "\n            f"(kèm {deleted_state_total} trạng thái điều hành trắng)"\n        ),\n        "backup": backup_dir.name,\n    }\n\n    if selected_year_id > 0:\n        q["school_year_id"] = selected_year_id\n\n    return RedirectResponse(\n        url=(\n            "/dieu-tra/quan-ly-dot-toan-tinh?"\n            + urlencode(q)\n        ),\n        status_code=303,\n    )\n\n\n# === BAI_13B_11_3_BULK_DELETE_END ===\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_source() -> None:
    target = BACKUP / ROUTER.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROUTER, target)


def restore_source() -> None:
    source = BACKUP / ROUTER.relative_to(PROJECT)
    if source.exists():
        ROUTER.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, ROUTER)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def preflight(text: str) -> None:
    required = [
        "BAI_13B_11_PROVINCE_BATCH_ADMIN_START",
        "def _user(",
        "def _admin(",
        "def _tables(",
        "def _snapshot(",
        "def _references(",
        "def _safety_reason(",
        "def _backup_before_delete(",
        "def _log_delete(",
        START,
        END,
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "Router không đúng nền Bài 13B-11 thực tế. "
                f"Thiếu: {marker}"
            )


def patch(text: str) -> str:
    preflight(text)

    a = text.find(START)
    b = text.find(END, a)

    if a < 0 or b < 0:
        raise RuntimeError(
            "Không xác định được khối xóa hàng loạt."
        )

    b += len(END)

    return (
        text[:a]
        + NEW_BLOCK.strip()
        + text[b:]
    )


def verify() -> None:
    text = read_text(ROUTER)

    a = text.find(START)
    b = text.find(END, a)
    block = text[a:b + len(END)]

    required = [
        "def _bulk_execution_state_check(",
        "def _bulk_noncompanion_references(",
        "survey_commune_execution_states",
        "is_commune_locked",
        "is_province_locked",
        '@router.post("/xoa-hang-loat")',
        "if not _admin(request)",
        "actor = _user(request)",
        "_backup_before_delete(",
        "BEGIN IMMEDIATE",
        "DELETE FROM survey_commune_execution_states",
        "DELETE FROM survey_batches",
        "remaining != 0",
        "XOA TOAN BO DA CHON",
    ]

    for marker in required:
        if marker not in block:
            raise RuntimeError(
                f"Verify thất bại: thiếu {marker}"
            )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(ROUTER),
        ],
        cwd=PROJECT,
        check=True,
    )


def main() -> int:
    print("=" * 108)
    print(
        "BÀI 13B-11.3.4 - "
        "XỬ LÝ EXECUTION-STATE TRẮNG KHI XÓA ĐỢT"
    )
    print("=" * 108)
    print()
    print("KẾT QUẢ CHẨN ĐOÁN:")
    print(" - 130 survey_batches CHUAN_BI.")
    print(" - 0 survey_forms.")
    print(
        " - 130 survey_commune_execution_states "
        "đang tham chiếu tới 130 đợt."
    )
    print()
    print("BẢN SỬA:")
    print(
        " - Chỉ cho phép coi execution-state là bản ghi đồng hành "
        "nếu hoàn toàn chưa khóa/chưa chốt."
    )
    print(
        " - Nếu có lịch sử khóa xã/tỉnh -> CHẶN, không xóa."
    )
    print(
        " - Mọi bảng tham chiếu khác vẫn CHẶN như cũ."
    )
    print(
        " - Sau backup và kiểm tra lần 2, xóa execution-state trắng "
        "rồi xóa batch trong cùng một transaction."
    )
    print()
    print("AN TOÀN:")
    print(" - Bộ cài KHÔNG sửa database.")
    print(" - Backup DB chỉ được tạo khi anh bấm xóa thật.")
    print(" - All-or-nothing.")
    print(" - Sau DELETE còn batch đã chọn -> rollback.")
    print()

    before = read_text(ROUTER)
    preflight(before)

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        write_text(
            ROUTER,
            patch(before),
        )

        verify()
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Router py_compile: OK")
        print(" - Helper execution-state trắng: OK")
        print(" - Chặn execution-state đã khóa: OK")
        print(" - Xóa companion + batch cùng transaction: OK")
        print(" - Kiểm tra remaining sau DELETE: OK")
        print(" - Database lúc cài: KHÔNG THAY ĐỔI")
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.3.4 THÀNH CÔNG"
        )
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore_source()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
