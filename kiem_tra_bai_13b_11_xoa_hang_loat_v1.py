from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from datetime import datetime

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

ROUTER = (
    PROJECT
    / "app"
    / "routers"
    / "survey_batch_admin_v13b11.py"
)

TEMPLATE = (
    PROJECT
    / "app"
    / "templates"
    / "surveys"
    / "province_batch_admin_v13b11.html"
)

DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

SCHOOL_YEAR_ID = 8


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def extract_block(text: str, start: str, end: str) -> str:
    a = text.find(start)
    if a < 0:
        return ""
    b = text.find(end, a)
    if b < 0:
        return text[a:]
    return text[a:b + len(end)]


def list_helpers(text: str) -> list[str]:
    return re.findall(
        r"(?m)^def\s+(_[A-Za-z0-9_]+)\s*\(",
        text,
    )


def count_route(text: str, route: str) -> int:
    return text.count(f'@router.post("{route}")')


def db_report() -> None:
    print()
    print("=" * 90)
    print("3. DATABASE - CHỈ ĐỌC")
    print("=" * 90)

    if not DB.exists():
        print("KHÔNG TÌM THẤY DATABASE:", DB)
        return

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only=ON")

        total = con.execute(
            """
            SELECT COUNT(*)
            FROM survey_batches
            WHERE school_year_id = ?
            """,
            (SCHOOL_YEAR_ID,),
        ).fetchone()[0]

        print(f"school_year_id={SCHOOL_YEAR_ID} -> survey_batches = {total}")

        rows = con.execute(
            """
            SELECT status, COUNT(*)
            FROM survey_batches
            WHERE school_year_id = ?
            GROUP BY status
            ORDER BY status
            """,
            (SCHOOL_YEAR_ID,),
        ).fetchall()

        print("Theo trạng thái:")
        for status, count in rows:
            print(f" - {status}: {count}")

        # survey_forms nếu có
        tables = {
            row[0]
            for row in con.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                """
            ).fetchall()
        }

        if "survey_forms" in tables:
            form_count = con.execute(
                """
                SELECT COUNT(*)
                FROM survey_forms sf
                JOIN survey_batches sb
                  ON sb.id = sf.survey_batch_id
                WHERE sb.school_year_id = ?
                """,
                (SCHOOL_YEAR_ID,),
            ).fetchone()[0]
            print("survey_forms thuộc năm học:", form_count)

        # Thống kê các bảng có cột survey_batch_id/batch_id và đang tham chiếu
        print()
        print("Các bảng có bản ghi tham chiếu tới đợt của năm học này:")
        refs_found = 0

        for table in sorted(tables):
            if table == "survey_batches":
                continue

            cols = {
                row[1]
                for row in con.execute(
                    f'PRAGMA table_info("{table.replace(chr(34), chr(34)*2)}")'
                ).fetchall()
            }

            candidate_cols = [
                col
                for col in (
                    "survey_batch_id",
                    "source_batch_id",
                    "target_batch_id",
                    "batch_id",
                )
                if col in cols
            ]

            for col in candidate_cols:
                safe_table = table.replace('"', '""')
                safe_col = col.replace('"', '""')
                try:
                    count = con.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM "{safe_table}" t
                        WHERE t."{safe_col}" IN (
                            SELECT id
                            FROM survey_batches
                            WHERE school_year_id = ?
                        )
                        """,
                        (SCHOOL_YEAR_ID,),
                    ).fetchone()[0]
                except sqlite3.Error:
                    continue

                if count:
                    refs_found += 1
                    print(f' - {table}.{col}: {count}')

        if refs_found == 0:
            print(" - Không phát hiện bản ghi tham chiếu theo các cột chuẩn.")

    finally:
        con.close()


def backup_report() -> None:
    print()
    print("=" * 90)
    print("4. BACKUP DO THAO TÁC XÓA HÀNG LOẠT")
    print("=" * 90)

    if not EXPORTS.exists():
        print("Không có thư mục exports.")
        return

    items = sorted(
        [
            p
            for p in EXPORTS.iterdir()
            if p.is_dir()
            and (
                p.name.startswith("backup_truoc_xoa_dot_HANG_LOAT_")
                or "HANG_LOAT" in p.name
            )
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not items:
        print(
            "CHƯA thấy backup HANG_LOAT nào -> "
            "request xóa có thể chưa đi tới bước backup."
        )
        return

    print(f"Tìm thấy {len(items)} backup HANG_LOAT. 5 bản mới nhất:")
    for p in items[:5]:
        when = datetime.fromtimestamp(
            p.stat().st_mtime
        ).strftime("%d/%m/%Y %H:%M:%S")
        print(f" - {when} | {p.name}")


def main() -> int:
    print("=" * 90)
    print("KIỂM TRA BÀI 13B-11 - XÓA HÀNG LOẠT V1")
    print("CHỈ ĐỌC - KHÔNG SỬA SOURCE - KHÔNG SỬA DATABASE")
    print("=" * 90)

    router = read_text(ROUTER)
    template = read_text(TEMPLATE)

    print()
    print("=" * 90)
    print("1. ROUTER HIỆN TẠI")
    print("=" * 90)
    print("Router:", ROUTER)
    print("Tồn tại:", ROUTER.exists())
    print("Kích thước:", ROUTER.stat().st_size if ROUTER.exists() else 0)

    if router:
        helpers = list_helpers(router)
        print("Helper tìm thấy:")
        print(" ", ", ".join(helpers) if helpers else "(không có)")

        checks = [
            "BAI_13B_11_PROVINCE_BATCH_ADMIN_START",
            "BAI_13B_11_3_BULK_DELETE_START",
            "BAI_13B_11_3_BULK_DELETE_END",
            'def _user(',
            'def _admin(',
            'def _snapshot(',
            'def _references(',
            'def _safety_reason(',
            'def _backup_before_delete(',
            'def _log_delete(',
            'if not _admin(request)',
            'actor = _user(request)',
            'BEGIN IMMEDIATE',
            'DELETE FROM survey_batches',
            'XOA TOAN BO DA CHON',
        ]

        print()
        print("Marker quan trọng:")
        for marker in checks:
            print(
                f" - {'OK' if marker in router else 'THIẾU'} | {marker}"
            )

        print()
        print(
            "Số route POST /xoa-hang-loat:",
            count_route(router, "/xoa-hang-loat"),
        )

        block = extract_block(
            router,
            "# === BAI_13B_11_3_BULK_DELETE_START ===",
            "# === BAI_13B_11_3_BULK_DELETE_END ===",
        )

        if block:
            print()
            print("Đầu khối backend xóa hàng loạt hiện tại:")
            print("-" * 90)
            print("\n".join(block.splitlines()[:80]))
            print("-" * 90)
        else:
            print("KHÔNG TÌM THẤY KHỐI BACKEND XÓA HÀNG LOẠT.")

    print()
    print("=" * 90)
    print("2. TEMPLATE HIỆN TẠI")
    print("=" * 90)
    print("Template:", TEMPLATE)
    print("Tồn tại:", TEMPLATE.exists())

    template_checks = [
        "b1311-select-all-checkbox",
        "b1311-bulk-delete-form",
        "b1311-bulk-delete-button",
        "/dieu-tra/quan-ly-dot-toan-tinh/xoa-hang-loat",
        "XOA TOAN BO DA CHON",
        'name="batch_ids"',
        'data-batch-id=',
    ]

    for marker in template_checks:
        print(
            f" - {'OK' if marker in template else 'THIẾU'} | {marker}"
        )

    db_report()
    backup_report()

    print()
    print("=" * 90)
    print("KẾT THÚC KIỂM TRA")
    print("=" * 90)
    print(
        "Hãy chụp hoặc copy toàn bộ kết quả từ "
        "'1. ROUTER HIỆN TẠI' đến '4. BACKUP' gửi lại."
    )
    print(
        "Script này không có INSERT/UPDATE/DELETE và mở database ở mode=ro."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
