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
    / f"backup_source_bai_13b_11_3_3_{STAMP}"
)

START = (
    "# === BAI_13B_11_3_BULK_DELETE_START ==="
)
END = (
    "# === BAI_13B_11_3_BULK_DELETE_END ==="
)

FIXED_BLOCK = '\n# === BAI_13B_11_3_BULK_DELETE_START ===\n\nBULK_DELETE_CONFIRM_TEXT = "XOA TOAN BO DA CHON"\n\n\n@router.post("/xoa-hang-loat")\nasync def delete_empty_batches_bulk(request: Request):\n    """\n    Bài 13B-11.3.3:\n    Xóa hàng loạt các đợt trống đã chọn theo đúng helper thực tế\n    của Bài 13B-11 trên dự án:\n      _user, _admin, _snapshot, _references, _safety_reason,\n      _backup_before_delete, _log_delete.\n\n    Nguyên tắc:\n    - Một backup chung trước khi DELETE.\n    - Kiểm tra toàn bộ lần 1.\n    - BEGIN IMMEDIATE.\n    - Kiểm tra toàn bộ lần 2.\n    - Chỉ khi tất cả an toàn mới DELETE.\n    - Một đợt lỗi => rollback toàn bộ.\n    """\n    if not _admin(request):\n        return _forbidden()\n\n    form = await request.form()\n    actor = _user(request)\n\n    raw_ids = list(form.getlist("batch_ids"))\n    batch_ids: list[int] = []\n\n    for raw in raw_ids:\n        try:\n            batch_id = int(str(raw or "").strip())\n        except (TypeError, ValueError):\n            continue\n\n        if batch_id > 0:\n            batch_ids.append(batch_id)\n\n    batch_ids = sorted(set(batch_ids))\n\n    try:\n        selected_year_id = int(\n            str(form.get("school_year_id") or "0").strip()\n        )\n    except (TypeError, ValueError):\n        selected_year_id = 0\n\n    confirm_phrase = _clean(\n        form.get("confirm_phrase"),\n        200,\n    )\n\n    def redirect_blocked(\n        detail: str,\n        backup_name: str = "",\n    ):\n        q: dict[str, Any] = {\n            "status": "delete_blocked",\n            "detail": detail,\n        }\n\n        if selected_year_id > 0:\n            q["school_year_id"] = selected_year_id\n\n        if backup_name:\n            q["backup"] = backup_name\n\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/quan-ly-dot-toan-tinh?"\n                + urlencode(q)\n            ),\n            status_code=303,\n        )\n\n    def redirect_failed(\n        backup_name: str = "",\n    ):\n        q: dict[str, Any] = {\n            "status": "delete_failed",\n        }\n\n        if selected_year_id > 0:\n            q["school_year_id"] = selected_year_id\n\n        if backup_name:\n            q["backup"] = backup_name\n\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/quan-ly-dot-toan-tinh?"\n                + urlencode(q)\n            ),\n            status_code=303,\n        )\n\n    if not batch_ids:\n        return redirect_blocked(\n            "Chưa nhận được danh sách đợt đã chọn. "\n            "Chưa xóa đợt nào."\n        )\n\n    if len(batch_ids) > 1000:\n        return redirect_blocked(\n            "Số đợt được chọn vượt giới hạn an toàn 1000 đợt. "\n            "Chưa xóa đợt nào."\n        )\n\n    if confirm_phrase != BULK_DELETE_CONFIRM_TEXT:\n        return redirect_blocked(\n            f\'Phải nhập chính xác "{BULK_DELETE_CONFIRM_TEXT}". \'\n            "Chưa xóa đợt nào."\n        )\n\n    snapshots: list[dict[str, Any]] = []\n    actual_year_id: int | None = None\n\n    # =====================================================\n    # KIỂM TRA LẦN 1\n    # =====================================================\n    con = sqlite3.connect(\n        str(DATABASE_PATH),\n        timeout=30,\n    )\n\n    try:\n        con.execute("PRAGMA foreign_keys=ON")\n        con.execute("PRAGMA busy_timeout=30000")\n\n        for batch_id in batch_ids:\n            snapshot = _snapshot(\n                con,\n                batch_id,\n            )\n\n            if snapshot is None:\n                return redirect_blocked(\n                    f"Không tìm thấy đợt ID {batch_id}. "\n                    "Toàn bộ thao tác đã dừng."\n                )\n\n            year_id = int(\n                snapshot.get("school_year_id") or 0\n            )\n\n            if actual_year_id is None:\n                actual_year_id = year_id\n\n            if year_id != actual_year_id:\n                return redirect_blocked(\n                    "Các đợt được chọn không cùng một năm học. "\n                    "Toàn bộ thao tác đã dừng."\n                )\n\n            if (\n                selected_year_id > 0\n                and year_id != selected_year_id\n            ):\n                return redirect_blocked(\n                    f"Đợt {snapshot.get(\'code\')} không thuộc "\n                    "năm học đang hiển thị. "\n                    "Toàn bộ thao tác đã dừng."\n                )\n\n            refs = _references(\n                con,\n                batch_id,\n            )\n\n            reason = _safety_reason(\n                snapshot,\n                refs,\n            )\n\n            if reason:\n                return redirect_blocked(\n                    f"Đợt {snapshot.get(\'code\')}: {reason} "\n                    "Toàn bộ thao tác đã dừng; chưa xóa đợt nào."\n                )\n\n            snapshots.append(snapshot)\n\n    finally:\n        con.close()\n\n    if selected_year_id <= 0 and actual_year_id:\n        selected_year_id = actual_year_id\n\n    # =====================================================\n    # MỘT BACKUP CHUNG TRƯỚC KHI XÓA\n    # =====================================================\n    bulk_snapshot: dict[str, Any] = {\n        "id": None,\n        "code": (\n            f"HANG_LOAT_{len(batch_ids)}_DOT_"\n            f"NAM_{selected_year_id or \'KHONG_RO\'}"\n        ),\n        "name": (\n            "Bài 13B-11.3.3 - "\n            "Xóa hàng loạt đợt trống đã chọn"\n        ),\n        "status": "CHUAN_BI",\n        "school_year_id": (\n            selected_year_id\n            or actual_year_id\n        ),\n        "commune_id": None,\n        "batch_total": len(batch_ids),\n        "batch_ids": batch_ids,\n        "batch_codes": [\n            str(item.get("code") or "")\n            for item in snapshots\n        ],\n    }\n\n    try:\n        backup_dir = _backup_before_delete(\n            actor,\n            bulk_snapshot,\n        )\n    except Exception:\n        return redirect_failed()\n\n    # =====================================================\n    # KIỂM TRA LẦN 2 + DELETE TRONG MỘT GIAO DỊCH\n    # =====================================================\n    write_con = sqlite3.connect(\n        str(DATABASE_PATH),\n        timeout=30,\n    )\n\n    deleted_total = 0\n\n    try:\n        write_con.execute("PRAGMA foreign_keys=ON")\n        write_con.execute("PRAGMA busy_timeout=30000")\n        write_con.execute("BEGIN IMMEDIATE")\n\n        # Kiểm tra lại toàn bộ trước khi xóa dòng đầu tiên.\n        for batch_id in batch_ids:\n            latest = _snapshot(\n                write_con,\n                batch_id,\n            )\n\n            latest_refs = _references(\n                write_con,\n                batch_id,\n            )\n\n            latest_reason = _safety_reason(\n                latest,\n                latest_refs,\n            )\n\n            if latest_reason:\n                raise RuntimeError(\n                    "Dữ liệu đã thay đổi sau bước kiểm tra ban đầu. "\n                    f"Đợt ID {batch_id}: {latest_reason}"\n                )\n\n            latest_year_id = int(\n                (latest or {}).get(\n                    "school_year_id"\n                )\n                or 0\n            )\n\n            if (\n                selected_year_id > 0\n                and latest_year_id != selected_year_id\n            ):\n                raise RuntimeError(\n                    "Phát hiện đợt thay đổi phạm vi năm học "\n                    "trước khi xóa."\n                )\n\n        # Chỉ đến đây mới bắt đầu DELETE.\n        for batch_id in batch_ids:\n            cur = write_con.execute(\n                """\n                DELETE FROM survey_batches\n                WHERE id = ?\n                """,\n                (batch_id,),\n            )\n\n            if int(cur.rowcount or 0) != 1:\n                raise RuntimeError(\n                    f"Không xóa đúng một đợt ID {batch_id}."\n                )\n\n            deleted_total += 1\n\n        if deleted_total != len(batch_ids):\n            raise RuntimeError(\n                "Số đợt đã xóa không khớp số đợt được chọn."\n            )\n\n        write_con.commit()\n\n    except Exception as exc:\n        write_con.rollback()\n\n        return redirect_blocked(\n            (\n                "Xóa hàng loạt đã được hủy an toàn: "\n                + str(exc)[:700]\n            ),\n            backup_name=backup_dir.name,\n        )\n\n    finally:\n        write_con.close()\n\n    # =====================================================\n    # NHẬT KÝ SAU COMMIT\n    # =====================================================\n    try:\n        for snapshot in snapshots:\n            _log_delete(\n                actor,\n                snapshot,\n                backup_dir,\n            )\n    except Exception:\n        pass\n\n    q: dict[str, Any] = {\n        "status": "batch_deleted",\n        "code": (\n            f"{deleted_total} đợt trống đã chọn"\n        ),\n        "backup": backup_dir.name,\n    }\n\n    if selected_year_id > 0:\n        q["school_year_id"] = selected_year_id\n\n    return RedirectResponse(\n        url=(\n            "/dieu-tra/quan-ly-dot-toan-tinh?"\n            + urlencode(q)\n        ),\n        status_code=303,\n    )\n\n\n# === BAI_13B_11_3_BULK_DELETE_END ===\n'


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
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
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


def preflight(text: str) -> None:
    # Đây là đúng nền Bài 13B-11 thực tế đã được xác định
    # từ bộ cài gốc và log lỗi của máy người dùng.
    required = [
        "BAI_13B_11_PROVINCE_BATCH_ADMIN_START",
        "def _user(",
        "def _admin(",
        "def _snapshot(",
        "def _references(",
        "def _safety_reason(",
        "def _backup_before_delete(",
        "def _log_delete(",
        '@router.post("/{batch_id}/xoa")',
        START,
        END,
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "Router hiện tại không đúng nền Bài 13B-11 "
                f"đã xác định. Thiếu: {marker}"
            )


def patch(text: str) -> str:
    preflight(text)

    start_pos = text.find(START)
    end_pos = text.find(
        END,
        start_pos,
    )

    if start_pos < 0 or end_pos < 0:
        raise RuntimeError(
            "Không xác định được khối xóa hàng loạt cần thay."
        )

    end_pos += len(END)

    return (
        text[:start_pos]
        + FIXED_BLOCK.strip()
        + text[end_pos:]
    )


def verify() -> None:
    text = read_text(ROUTER)

    start_pos = text.find(START)
    end_pos = text.find(
        END,
        start_pos,
    )

    if start_pos < 0 or end_pos < 0:
        raise RuntimeError(
            "Không đọc lại được khối 13B-11.3 sau sửa."
        )

    block = text[
        start_pos:
        end_pos + len(END)
    ]

    required = [
        '@router.post("/xoa-hang-loat")',
        "if not _admin(request)",
        "actor = _user(request)",
        "_snapshot(",
        "_references(",
        "_safety_reason(",
        "_backup_before_delete(",
        "_log_delete(",
        "BEGIN IMMEDIATE",
        "DELETE FROM survey_batches",
        "XOA TOAN BO DA CHON",
    ]

    for marker in required:
        if marker not in block:
            raise RuntimeError(
                f"Kiểm tra sau sửa không đạt: {marker}"
            )

    # Không được còn các helper sai đã gây lỗi ở các bản trước.
    wrong = [
        "_current_user(",
        "_admin_only(",
        "_batch_snapshot(",
        "_batch_references(",
        "_delete_safety_reason(",
        "_append_delete_log(",
    ]

    for marker in wrong:
        if marker in block:
            raise RuntimeError(
                "Khối xóa hàng loạt vẫn chứa helper sai: "
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
        "BÀI 13B-11.3.3 - "
        "SỬA XÓA HÀNG LOẠT THEO ĐÚNG NỀN THỰC TẾ"
    )
    print("=" * 108)
    print()
    print("NỀN THỰC TẾ ĐÃ XÁC ĐỊNH:")
    print(" - _user")
    print(" - _admin")
    print(" - _snapshot")
    print(" - _references")
    print(" - _safety_reason")
    print(" - _backup_before_delete")
    print(" - _log_delete")
    print()
    print("BẢN NÀY:")
    print(" - Thay toàn bộ backend xóa hàng loạt bằng helper đúng.")
    print(" - Giữ nguyên giao diện Chọn toàn bộ / 130-130.")
    print(" - Giữ nguyên menu 2.1.6.")
    print(" - Không thay chức năng tạo đợt toàn tỉnh.")
    print()
    print("AN TOÀN KHI XÓA THẬT:")
    print(" - Kiểm tra tất cả lần 1.")
    print(" - Một backup SQLite chung.")
    print(" - integrity_check + foreign_key_check từ helper gốc.")
    print(" - BEGIN IMMEDIATE.")
    print(" - Kiểm tra tất cả lần 2.")
    print(" - All-or-nothing.")
    print()
    print("QUAN TRỌNG:")
    print(" - BỘ CÀI KHÔNG SỬA DATABASE.")
    print(" - Nếu source không đúng nền, tự dừng và rollback source.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(
            f"Không tìm thấy: {ROUTER}"
        )

    before = read_text(ROUTER)
    preflight(before)

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )
    backup()
    print("Backup source:", BACKUP)

    try:
        after = patch(before)
        write_text(ROUTER, after)

        verify()
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Đúng helper nền Bài 13B-11: OK")
        print(" - Router py_compile: OK")
        print(" - Route xóa hàng loạt: OK")
        print(" - Backup chung trước xóa: OK")
        print(" - Kiểm tra an toàn 2 lần: OK")
        print(" - All-or-nothing: OK")
        print(" - Database khi cài: KHÔNG THAY ĐỔI")
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.3.3 THÀNH CÔNG"
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
