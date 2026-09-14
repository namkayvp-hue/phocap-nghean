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
    / f"backup_source_bai_13b_11_3_2_{STAMP}"
)

START = (
    "# === BAI_13B_11_3_BULK_DELETE_START ==="
)
END = (
    "# === BAI_13B_11_3_BULK_DELETE_END ==="
)

FIXED_BLOCK = '\n# === BAI_13B_11_3_BULK_DELETE_START ===\n\nBULK_DELETE_CONFIRM_TEXT = "XOA TOAN BO DA CHON"\n\n\n@router.post("/xoa-hang-loat")\nasync def delete_empty_batches_bulk(request: Request):\n    """\n    Bài 13B-11.3.2:\n    Xóa hàng loạt các đợt trống đã chọn theo nguyên tắc all-or-nothing.\n\n    - Chỉ ADMIN/Sở.\n    - Tất cả đợt phải cùng năm học đang hiển thị.\n    - Kiểm tra an toàn lần 1.\n    - Tạo 1 backup SQLite đầy đủ.\n    - BEGIN IMMEDIATE.\n    - Kiểm tra an toàn lần 2.\n    - Chỉ khi toàn bộ đạt mới DELETE.\n    - Một đợt lỗi => rollback toàn bộ.\n    """\n    if not _admin_only(request):\n        return _forbidden()\n\n    form = await request.form()\n    actor = _current_user(request)\n\n    raw_ids = list(form.getlist("batch_ids"))\n    batch_ids: list[int] = []\n\n    for raw in raw_ids:\n        try:\n            batch_id = int(str(raw or "").strip())\n        except (TypeError, ValueError):\n            continue\n\n        if batch_id > 0:\n            batch_ids.append(batch_id)\n\n    batch_ids = sorted(set(batch_ids))\n\n    try:\n        selected_year_id = int(\n            str(form.get("school_year_id") or "0").strip()\n        )\n    except (TypeError, ValueError):\n        selected_year_id = 0\n\n    confirm_phrase = _clean(\n        form.get("confirm_phrase"),\n        200,\n    )\n\n    def _redirect_blocked(\n        detail: str,\n        *,\n        backup_name: str = "",\n    ):\n        query_data: dict[str, Any] = {\n            "status": "delete_blocked",\n            "detail": detail,\n        }\n        if selected_year_id > 0:\n            query_data["school_year_id"] = selected_year_id\n        if backup_name:\n            query_data["backup"] = backup_name\n\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/quan-ly-dot-toan-tinh?"\n                + urlencode(query_data)\n            ),\n            status_code=303,\n        )\n\n    def _redirect_failed(\n        *,\n        backup_name: str = "",\n    ):\n        query_data: dict[str, Any] = {\n            "status": "delete_failed",\n        }\n        if selected_year_id > 0:\n            query_data["school_year_id"] = selected_year_id\n        if backup_name:\n            query_data["backup"] = backup_name\n\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/quan-ly-dot-toan-tinh?"\n                + urlencode(query_data)\n            ),\n            status_code=303,\n        )\n\n    if not batch_ids:\n        return _redirect_blocked(\n            "Chưa nhận được danh sách đợt đã chọn. "\n            "Chưa xóa đợt nào."\n        )\n\n    if len(batch_ids) > 1000:\n        return _redirect_blocked(\n            "Số đợt được chọn vượt giới hạn an toàn 1000 đợt. "\n            "Chưa xóa đợt nào."\n        )\n\n    if confirm_phrase != BULK_DELETE_CONFIRM_TEXT:\n        return _redirect_blocked(\n            f\'Phải nhập chính xác "{BULK_DELETE_CONFIRM_TEXT}". \'\n            "Chưa xóa đợt nào."\n        )\n\n    snapshots: list[dict[str, Any]] = []\n    actual_year_id: int | None = None\n\n    # =====================================================\n    # KIỂM TRA AN TOÀN LẦN 1\n    # =====================================================\n    con = sqlite3.connect(\n        str(DATABASE_PATH),\n        timeout=30,\n    )\n\n    try:\n        con.execute("PRAGMA foreign_keys=ON")\n        con.execute("PRAGMA busy_timeout=30000")\n\n        for batch_id in batch_ids:\n            snapshot = _batch_snapshot(\n                con,\n                batch_id,\n            )\n\n            if snapshot is None:\n                return _redirect_blocked(\n                    f"Không tìm thấy đợt ID {batch_id}. "\n                    "Toàn bộ thao tác đã dừng."\n                )\n\n            year_id = int(\n                snapshot.get("school_year_id") or 0\n            )\n\n            if actual_year_id is None:\n                actual_year_id = year_id\n\n            if year_id != actual_year_id:\n                return _redirect_blocked(\n                    "Danh sách đã chọn chứa đợt thuộc nhiều năm học. "\n                    "Toàn bộ thao tác đã dừng."\n                )\n\n            if (\n                selected_year_id > 0\n                and year_id != selected_year_id\n            ):\n                return _redirect_blocked(\n                    f"Đợt {snapshot.get(\'code\')} không thuộc "\n                    "năm học đang hiển thị. "\n                    "Toàn bộ thao tác đã dừng."\n                )\n\n            references = _batch_references(\n                con,\n                batch_id,\n            )\n\n            reason = _delete_safety_reason(\n                snapshot,\n                references,\n            )\n\n            if reason:\n                return _redirect_blocked(\n                    f"Đợt {snapshot.get(\'code\')}: {reason} "\n                    "Toàn bộ thao tác đã dừng; chưa xóa đợt nào."\n                )\n\n            snapshots.append(snapshot)\n\n    finally:\n        con.close()\n\n    if selected_year_id <= 0 and actual_year_id:\n        selected_year_id = actual_year_id\n\n    # =====================================================\n    # MỘT BACKUP CHUNG TRƯỚC KHI XÓA\n    # =====================================================\n    bulk_snapshot: dict[str, Any] = {\n        "id": None,\n        "code": (\n            f"HANG_LOAT_{len(batch_ids)}_DOT_"\n            f"NAM_{selected_year_id or \'KHONG_RO\'}"\n        ),\n        "name": (\n            "Bài 13B-11.3.2 - "\n            "Xóa hàng loạt đợt trống đã chọn"\n        ),\n        "status": "CHUAN_BI",\n        "school_year_id": (\n            selected_year_id\n            or actual_year_id\n        ),\n        "commune_id": None,\n        "batch_total": len(batch_ids),\n        "batch_ids": batch_ids,\n        "batch_codes": [\n            str(item.get("code") or "")\n            for item in snapshots\n        ],\n    }\n\n    try:\n        backup_dir = _backup_before_delete(\n            actor=actor,\n            snapshot=bulk_snapshot,\n        )\n\n    except Exception:\n        return _redirect_failed()\n\n    # =====================================================\n    # KIỂM TRA AN TOÀN LẦN 2 + DELETE TRONG 1 GIAO DỊCH\n    # =====================================================\n    write_con = sqlite3.connect(\n        str(DATABASE_PATH),\n        timeout=30,\n    )\n\n    deleted_total = 0\n\n    try:\n        write_con.execute("PRAGMA foreign_keys=ON")\n        write_con.execute("PRAGMA busy_timeout=30000")\n        write_con.execute("BEGIN IMMEDIATE")\n\n        # Kiểm tra lại TẤT CẢ trước khi xóa bản ghi đầu tiên.\n        for batch_id in batch_ids:\n            latest_snapshot = _batch_snapshot(\n                write_con,\n                batch_id,\n            )\n\n            latest_references = _batch_references(\n                write_con,\n                batch_id,\n            )\n\n            latest_reason = _delete_safety_reason(\n                latest_snapshot,\n                latest_references,\n            )\n\n            if latest_reason:\n                raise RuntimeError(\n                    "Dữ liệu đã thay đổi sau bước kiểm tra ban đầu. "\n                    f"Đợt ID {batch_id}: {latest_reason}"\n                )\n\n            latest_year_id = int(\n                (latest_snapshot or {}).get(\n                    "school_year_id"\n                )\n                or 0\n            )\n\n            if (\n                selected_year_id > 0\n                and latest_year_id != selected_year_id\n            ):\n                raise RuntimeError(\n                    "Phát hiện thay đổi phạm vi năm học "\n                    "trước khi xóa."\n                )\n\n        # Chỉ đến đây mới bắt đầu DELETE.\n        for batch_id in batch_ids:\n            cursor = write_con.execute(\n                """\n                DELETE FROM survey_batches\n                WHERE id = ?\n                """,\n                (batch_id,),\n            )\n\n            if int(cursor.rowcount or 0) != 1:\n                raise RuntimeError(\n                    f"Không xóa đúng một đợt ID {batch_id}."\n                )\n\n            deleted_total += 1\n\n        if deleted_total != len(batch_ids):\n            raise RuntimeError(\n                "Số đợt xóa thực tế không khớp số đợt đã chọn."\n            )\n\n        write_con.commit()\n\n    except Exception as exc:\n        write_con.rollback()\n\n        return _redirect_blocked(\n            (\n                "Xóa hàng loạt đã được hủy an toàn: "\n                + str(exc)[:700]\n            ),\n            backup_name=backup_dir.name,\n        )\n\n    finally:\n        write_con.close()\n\n    # =====================================================\n    # NHẬT KÝ SAU KHI COMMIT\n    # =====================================================\n    try:\n        for snapshot in snapshots:\n            _append_delete_log(\n                actor=actor,\n                snapshot=snapshot,\n                backup_dir=backup_dir,\n            )\n    except Exception:\n        # Không rollback giao dịch đã commit chỉ vì log phụ.\n        pass\n\n    query_data: dict[str, Any] = {\n        "status": "batch_deleted",\n        "code": (\n            f"{deleted_total} đợt trống đã chọn"\n        ),\n        "backup": backup_dir.name,\n    }\n\n    if selected_year_id > 0:\n        query_data["school_year_id"] = selected_year_id\n\n    return RedirectResponse(\n        url=(\n            "/dieu-tra/quan-ly-dot-toan-tinh?"\n            + urlencode(query_data)\n        ),\n        status_code=303,\n    )\n\n\n# === BAI_13B_11_3_BULK_DELETE_END ===\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy tệp bắt buộc: {path}"
        )
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup() -> None:
    target = BACKUP / ROUTER.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROUTER, target)


def restore() -> None:
    source = BACKUP / ROUTER.relative_to(PROJECT)
    if source.exists():
        ROUTER.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.copy2(source, ROUTER)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def patch(text: str) -> str:
    required_base = [
        "BAI_13B_11_PROVINCE_BATCH_ADMIN_START",
        "def _current_user(",
        "def _admin_only(",
        "def _batch_snapshot(",
        "def _batch_references(",
        "def _delete_safety_reason(",
        "def _backup_before_delete(",
        "def _append_delete_log(",
    ]

    for marker in required_base:
        if marker not in text:
            raise RuntimeError(
                "Router Bài 13B-11 không đúng nền cần sửa. "
                f"Thiếu: {marker}"
            )

    if START not in text or END not in text:
        raise RuntimeError(
            "Không tìm thấy khối backend xóa hàng loạt "
            "của Bài 13B-11.3."
        )

    start_pos = text.find(START)
    end_pos = text.find(END, start_pos)

    if start_pos < 0 or end_pos < 0:
        raise RuntimeError(
            "Không xác định được phạm vi khối cần thay."
        )

    end_pos += len(END)

    return (
        text[:start_pos]
        + FIXED_BLOCK.strip()
        + text[end_pos:]
    )


def verify() -> None:
    text = read_text(ROUTER)

    required = [
        "BAI_13B_11_3_BULK_DELETE_START",
        '@router.post("/xoa-hang-loat")',
        "if not _admin_only(request)",
        "actor = _current_user(request)",
        "_batch_snapshot(",
        "_batch_references(",
        "_delete_safety_reason(",
        "_backup_before_delete(",
        "actor=actor",
        "snapshot=bulk_snapshot",
        "_append_delete_log(",
        "BEGIN IMMEDIATE",
        "DELETE FROM survey_batches",
        "XOA TOAN BO DA CHON",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Kiểm tra sau sửa không đạt: {marker}"
            )

    # Những tên hàm sai của bản 13B-11.3 cũ
    # không được còn trong riêng khối bulk.
    start_pos = text.find(START)
    end_pos = text.find(END, start_pos)
    block = text[start_pos:end_pos]

    wrong_calls = [
        "if not _admin(request)",
        "actor = _user(request)",
        "_snapshot(con",
        "_references(con",
        "_safety_reason(",
        "_log_delete(",
    ]

    for marker in wrong_calls:
        if marker in block:
            raise RuntimeError(
                "Backend cũ sai tên hàm vẫn còn: "
                + marker
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
        "BÀI 13B-11.3.2 - "
        "SỬA BACKEND XÓA HÀNG LOẠT"
    )
    print("=" * 108)
    print()
    print("NGUYÊN NHÂN ĐÃ XÁC ĐỊNH:")
    print(
        " - Bản 13B-11.3 gọi sai tên helper "
        "của nền Bài 13B-11."
    )
    print(
        " - Vì vậy thao tác hàng loạt không đi tới DELETE."
    )
    print()
    print("BẢN SỬA:")
    print(" - Dùng đúng _admin_only / _current_user.")
    print(" - Dùng đúng _batch_snapshot.")
    print(" - Dùng đúng _batch_references.")
    print(" - Dùng đúng _delete_safety_reason.")
    print(
        " - Dùng đúng chữ ký _backup_before_delete "
        "(actor=, snapshot=)."
    )
    print(" - Dùng đúng _append_delete_log.")
    print()
    print("GIỮ NGUYÊN AN TOÀN:")
    print(" - 1 backup chung trước DELETE.")
    print(" - Kiểm tra tất cả đợt 2 lần.")
    print(" - BEGIN IMMEDIATE.")
    print(" - All-or-nothing.")
    print(
        " - 1 đợt lỗi => rollback, không xóa dở."
    )
    print()
    print("BỘ CÀI KHÔNG SỬA DATABASE.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(
            f"Không tìm thấy: {ROUTER}"
        )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )
    backup()
    print("Backup source:", BACKUP)

    try:
        before = read_text(ROUTER)
        after = patch(before)
        write_text(ROUTER, after)

        verify()
        clear_cache()

        print()
        print("KIỂM TRA SAU SỬA:")
        print(" - Router py_compile: OK")
        print(" - Helper names: OK")
        print(" - Backup call signature: OK")
        print(" - Transaction all-or-nothing: OK")
        print(
            " - Database trong lúc cài: KHÔNG THAY ĐỔI"
        )
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.3.2 THÀNH CÔNG"
        )
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC ROUTER..."
        )
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print(
            "Database không bị thay đổi bởi bộ cài."
        )
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
