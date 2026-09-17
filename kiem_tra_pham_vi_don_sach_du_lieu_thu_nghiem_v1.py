from __future__ import annotations

import sqlite3
from pathlib import Path
from collections import deque

PROJECT = Path(r"C:\PhoCap")
DB = PROJECT / "data" / "phocap.db"

# Dữ liệu người dùng yêu cầu giữ.
KEEP_BUSINESS = {
    "communes",                 # xã/phường
    "schools",                  # trường
    "classes",                  # lớp
    "staff_members",            # hồ sơ người thuộc đội ngũ
    "staff_year_records",       # hồ sơ đội ngũ theo năm
    "school_staff_year_summaries",
}

# Bảng hệ thống bắt buộc để ứng dụng còn hoạt động.
KEEP_SYSTEM = {
    "roles",
    "users",
    "school_years",
    "alembic_version",
}


def qi(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def tables(con: sqlite3.Connection) -> list[str]:
    return [
        str(r[0])
        for r in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]


def fks(con: sqlite3.Connection, table: str):
    result = []
    for row in con.execute(
        f"PRAGMA foreign_key_list({qi(table)})"
    ).fetchall():
        result.append({
            "parent": str(row[2]),
            "child_col": str(row[3]),
            "parent_col": str(row[4]),
        })
    return result


def count(con: sqlite3.Connection, table: str) -> int:
    try:
        return int(
            con.execute(
                f"SELECT COUNT(*) FROM {qi(table)}"
            ).fetchone()[0]
            or 0
        )
    except sqlite3.Error:
        return -1


def main() -> int:
    print('=' * 112)
    print('KIỂM TRA PHẠM VI DỌN SẠCH DỮ LIỆU THỬ NGHIỆM V1')
    print('CHỈ ĐỌC - KHÔNG INSERT / UPDATE / DELETE')
    print('=' * 112)

    if not DB.exists():
        print('Không tìm thấy database:', DB)
        return 1

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        con.execute('PRAGMA query_only=ON')
        all_tables = tables(con)
        all_set = set(all_tables)

        keep = (KEEP_BUSINESS | KEEP_SYSTEM) & all_set

        # Tự động giữ toàn bộ bảng CHA mà các bảng cần giữ phụ thuộc tới,
        # để không phá khóa ngoại.
        changed = True
        while changed:
            changed = False
            for child in list(keep):
                for fk in fks(con, child):
                    parent = fk['parent']
                    if parent in all_set and parent not in keep:
                        keep.add(parent)
                        changed = True

        print()
        print('1. BẢNG GIỮ LẠI')
        print('-' * 112)
        for table in sorted(keep):
            if table in KEEP_BUSINESS:
                reason = 'DỮ LIỆU CẦN GIỮ'
            elif table in KEEP_SYSTEM:
                reason = 'HỆ THỐNG BẮT BUỘC'
            else:
                reason = 'CHA FK CỦA BẢNG CẦN GIỮ'
            print(f'GIỮ  | {table:<45} | {count(con, table):>8} bản ghi | {reason}')

        print()
        print('2. BẢNG DỰ KIẾN XÓA SẠCH DỮ LIỆU')
        print('-' * 112)
        delete_tables = [t for t in all_tables if t not in keep]
        total_delete_rows = 0
        for table in delete_tables:
            c = count(con, table)
            if c > 0:
                total_delete_rows += c
            print(f'XÓA  | {table:<45} | {c:>8} bản ghi')

        print()
        print('3. KIỂM TRA BẢNG DỰ KIẾN XÓA CÓ ĐƯỢC BẢNG GIỮ THAM CHIẾU KHÔNG')
        print('-' * 112)
        dangerous = []
        for child in sorted(keep):
            for fk in fks(con, child):
                if fk['parent'] in delete_tables:
                    dangerous.append((child, fk['child_col'], fk['parent']))

        if dangerous:
            print('CẢNH BÁO - CHƯA ĐƯỢC XÓA:')
            for child, col, parent in dangerous:
                print(f' - {child}.{col} -> {parent}')
        else:
            print('ĐẠT: Không có bảng GIỮ nào tham chiếu tới bảng DỰ KIẾN XÓA qua FK.')

        print()
        print('4. THỐNG KÊ NHÓM QUAN TRỌNG')
        print('-' * 112)
        for table in (
            'communes', 'schools', 'classes', 'users', 'roles', 'school_years',
            'staff_members', 'staff_year_records', 'school_staff_year_summaries',
            'students', 'student_enrollments',
            'households', 'survey_people', 'survey_batches', 'survey_forms',
            'historical_datasets', 'historical_data_logs',
            'import_batches', 'student_change_logs',
        ):
            if table in all_set:
                print(f' - {table:<40}: {count(con, table)}')

        print()
        print('5. TÓM TẮT')
        print('-' * 112)
        print('Tổng số bảng hiện có       :', len(all_tables))
        print('Số bảng sẽ giữ             :', len(keep))
        print('Số bảng dự kiến dọn sạch   :', len(delete_tables))
        print('Tổng bản ghi dự kiến xóa   :', total_delete_rows)
        print('Cảnh báo FK từ bảng giữ    :', len(dangerous))
        print()
        print('Hãy COPY TOÀN BỘ KẾT QUẢ NÀY gửi lại ChatGPT.')
        print('Script chỉ đọc database bằng mode=ro và PRAGMA query_only=ON.')

    finally:
        con.close()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
