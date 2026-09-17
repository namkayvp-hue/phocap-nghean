# -*- coding: utf-8 -*-
"""
BÀI 13B-11.15.2.4.9.0.3
Ghi cờ is_special_difficulty_area cho 51 xã đặc biệt khó khăn tỉnh Nghệ An.

ĐIỀU KIỆN ĐẦU VÀO:
- Kết quả Bài 4.9.0.2 đã xác định đủ 51/51 xã trong bảng communes.
- Database hiện tại: C:\PhoCap\data\phocap.db
- Bảng: communes
- Cột tên: name

NGUYÊN TẮC AN TOÀN:
1) Kiểm tra đủ 51 bản ghi theo ID + mã xã + tên hiện tại.
2) Tạo backup SQLite trước khi đụng vào database.
3) Chỉ sau khi kiểm tra đạt mới mở transaction ghi dữ liệu.
4) Nếu chưa có cột is_special_difficulty_area thì tạo:
       INTEGER NOT NULL DEFAULT 0
5) Đặt toàn bộ 130 xã/phường = 0, sau đó đặt đúng 51 xã = 1.
6) Kiểm tra bắt buộc sau ghi:
       Tổng = 130
       TRUE = 51
       FALSE = 79
7) Nếu bất kỳ kiểm tra nào sai -> ROLLBACK.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


DB_DEFAULT = Path(r"C:\PhoCap\data\phocap.db")
FLAG_COLUMN = "is_special_difficulty_area"

# Danh sách đã được khóa từ kết quả đối chiếu 51/51.
# Dùng ID + mã + tên hiện có trong chính database để tránh cập nhật nhầm.
SPECIAL_COMMUNES: List[Dict[str, object]] = [
    {"id": 15,  "code": "16813", "name": "Xã Mường Xén"},
    {"id": 23,  "code": "16849", "name": "Xã Hữu Kiệm"},
    {"id": 22,  "code": "16837", "name": "Xã Nậm Cắn"},
    {"id": 24,  "code": "16855", "name": "Xã Chiêu Lưu"},
    {"id": 21,  "code": "16834", "name": "Xã Na Loi"},
    {"id": 25,  "code": "16858", "name": "Xã Mường Típ"},
    {"id": 26,  "code": "16870", "name": "Xã Na Ngoi"},
    {"id": 16,  "code": "16816", "name": "Xã Mỹ Lý"},
    {"id": 17,  "code": "16819", "name": "Xã Bắc Lý"},
    {"id": 18,  "code": "16822", "name": "Xã Keng Đu"},
    {"id": 19,  "code": "16828", "name": "Xã Huồi Tụ"},
    {"id": 20,  "code": "16831", "name": "Xã Mường Lống"},
    {"id": 27,  "code": "16876", "name": "Xã Tương Dương"},
    {"id": 34,  "code": "16933", "name": "Xã Tam Quang"},
    {"id": 35,  "code": "16936", "name": "Xã Tam Thái"},
    {"id": 31,  "code": "16906", "name": "Xã Lượng Minh"},
    {"id": 33,  "code": "16912", "name": "Xã Yên Na"},
    {"id": 32,  "code": "16909", "name": "Xã Yên Hòa"},
    {"id": 30,  "code": "16903", "name": "Xã Nga My"},
    {"id": 29,  "code": "16885", "name": "Xã Hữu Khuông"},
    {"id": 28,  "code": "16882", "name": "Xã Nhôn Mai"},
    {"id": 67,  "code": "17254", "name": "Xã Con Cuông"},
    {"id": 68,  "code": "17263", "name": "Xã Môn Sơn"},
    {"id": 66,  "code": "17248", "name": "Xã Châu Khê"},
    {"id": 65,  "code": "17242", "name": "Xã Cam Phục"},
    {"id": 64,  "code": "17239", "name": "Xã Mậu Thạch"},
    {"id": 63,  "code": "17230", "name": "Xã Bình Chuẩn"},
    {"id": 80,  "code": "17365", "name": "Xã Anh Sơn Đông"},
    {"id": 77,  "code": "17335", "name": "Xã Thành Bình Thọ"},
    {"id": 109, "code": "17759", "name": "Xã Sơn Lâm"},
    {"id": 73,  "code": "17287", "name": "Xã Tiên Đồng"},
    {"id": 71,  "code": "17278", "name": "Xã Giai Xuân"},
    {"id": 75,  "code": "17326", "name": "Xã Nghĩa Hành"},
    {"id": 6,   "code": "16738", "name": "Xã Quế Phong"},
    {"id": 7,   "code": "16744", "name": "Xã Thông Thụ"},
    {"id": 8,   "code": "16750", "name": "Xã Tiền Phong"},
    # QĐ 60 và DB hiện tại dùng "Mường Quàng".
    # Tài liệu tổng hợp 51 xã có chỗ ghi "Mường Quảng".
    # Ta khóa theo chính DB đã đối chiếu + phụ lục QĐ 60.
    {"id": 10,  "code": "16774", "name": "Xã Mường Quàng"},
    {"id": 9,   "code": "16756", "name": "Xã Tri Lễ"},
    {"id": 11,  "code": "16777", "name": "Xã Quỳ Châu"},
    {"id": 12,  "code": "16792", "name": "Xã Châu Tiến"},
    {"id": 13,  "code": "16801", "name": "Xã Hùng Chân"},
    {"id": 14,  "code": "16804", "name": "Xã Châu Bình"},
    {"id": 46,  "code": "17035", "name": "Xã Quỳ Hợp"},
    {"id": 50,  "code": "17071", "name": "Xã Minh Hợp"},
    {"id": 48,  "code": "17056", "name": "Xã Châu Lộc"},
    {"id": 51,  "code": "17077", "name": "Xã Mường Ham"},
    {"id": 49,  "code": "17059", "name": "Xã Tam Hợp"},
    {"id": 52,  "code": "17089", "name": "Xã Mường Chọng"},
    {"id": 47,  "code": "17044", "name": "Xã Châu Hồng"},
    {"id": 39,  "code": "16969", "name": "Xã Nghĩa Thọ"},
    {"id": 62,  "code": "17224", "name": "Xã Quỳnh Thắng"},
]

EXPECTED_TOTAL = 130
EXPECTED_TRUE = 51
EXPECTED_FALSE = 79


def find_db() -> Path:
    candidates = [
        DB_DEFAULT,
        Path.cwd() / "data" / "phocap.db",
        Path.cwd() / "phocap.db",
        Path(__file__).resolve().parent / "data" / "phocap.db",
        Path(__file__).resolve().parent / "phocap.db",
    ]

    for p in candidates:
        if p.is_file():
            return p.resolve()

    raise FileNotFoundError(
        "Không tìm thấy phocap.db. "
        "Hãy đặt script trong C:\\PhoCap và bảo đảm database ở C:\\PhoCap\\data\\phocap.db."
    )


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def columns_of(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    return [str(r[1]) for r in rows]


def validate_source_list() -> None:
    if len(SPECIAL_COMMUNES) != EXPECTED_TRUE:
        raise RuntimeError(
            f"Danh sách khóa phải có đúng {EXPECTED_TRUE} xã, "
            f"hiện có {len(SPECIAL_COMMUNES)}."
        )

    ids = [int(x["id"]) for x in SPECIAL_COMMUNES]
    codes = [str(x["code"]) for x in SPECIAL_COMMUNES]

    if len(set(ids)) != EXPECTED_TRUE:
        raise RuntimeError("Danh sách 51 xã có ID bị trùng.")
    if len(set(codes)) != EXPECTED_TRUE:
        raise RuntimeError("Danh sách 51 xã có mã xã bị trùng.")


def verify_database_identity(conn: sqlite3.Connection) -> None:
    """
    Không ghi gì ở bước này.
    Chỉ cho phép tiếp tục nếu DB hiện tại đúng với DB đã được đối chiếu.
    """
    if not table_exists(conn, "communes"):
        raise RuntimeError("Không có bảng communes.")

    cols = columns_of(conn, "communes")
    for required in ("id", "code", "name"):
        if required not in cols:
            raise RuntimeError(f"Bảng communes thiếu cột bắt buộc: {required}")

    total = conn.execute("SELECT COUNT(*) FROM communes").fetchone()[0]
    if total != EXPECTED_TOTAL:
        raise RuntimeError(
            f"Database hiện có {total} xã/phường, không phải {EXPECTED_TOTAL}. "
            "Dừng để tránh cập nhật nhầm database."
        )

    errors: List[str] = []

    for item in SPECIAL_COMMUNES:
        row = conn.execute(
            "SELECT id, code, name FROM communes WHERE id=?",
            (int(item["id"]),),
        ).fetchone()

        if row is None:
            errors.append(
                f"ID {item['id']}: không tồn tại; dự kiến {item['name']} / {item['code']}"
            )
            continue

        db_id, db_code, db_name = row
        if str(db_code) != str(item["code"]) or str(db_name).strip() != str(item["name"]).strip():
            errors.append(
                f"ID {item['id']}: DB='{db_name}' / {db_code}; "
                f"dự kiến='{item['name']}' / {item['code']}"
            )

    if errors:
        msg = [
            "Database hiện tại không còn giống kết quả đối chiếu 4.9.0.2.",
            "DỪNG, KHÔNG GHI.",
            "",
        ]
        msg.extend(errors)
        raise RuntimeError("\n".join(msg))


def make_backup(db_path: Path) -> Path:
    """
    Backup bằng SQLite Backup API.
    Tạo file độc lập trước khi cập nhật.
    """
    backup_dir = db_path.parent.parent / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"backup_truoc_bai_13b_11_15_2_4_9_0_3_{stamp}.db"

    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(backup_path))
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()

    # Kiểm tra backup mở được và integrity OK.
    check = sqlite3.connect(str(backup_path))
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        if str(integrity).lower() != "ok":
            raise RuntimeError(f"Backup integrity_check không đạt: {integrity}")

        total = check.execute("SELECT COUNT(*) FROM communes").fetchone()[0]
        if total != EXPECTED_TOTAL:
            raise RuntimeError(
                f"Backup có {total} bản ghi communes, không phải {EXPECTED_TOTAL}."
            )
    finally:
        check.close()

    return backup_path


def ensure_flag_column(conn: sqlite3.Connection) -> bool:
    """
    Trả về True nếu vừa tạo cột mới, False nếu cột đã có.
    """
    cols = columns_of(conn, "communes")
    if FLAG_COLUMN in cols:
        return False

    conn.execute(
        f"""
        ALTER TABLE communes
        ADD COLUMN {quote_ident(FLAG_COLUMN)} INTEGER NOT NULL DEFAULT 0
        """
    )
    return True


def update_flags(conn: sqlite3.Connection) -> Tuple[int, int, int]:
    ids = [int(x["id"]) for x in SPECIAL_COMMUNES]

    # Khóa toàn bộ danh mục về FALSE trước.
    conn.execute(
        f"UPDATE communes SET {quote_ident(FLAG_COLUMN)} = 0"
    )

    placeholders = ",".join("?" for _ in ids)
    cur = conn.execute(
        f"""
        UPDATE communes
        SET {quote_ident(FLAG_COLUMN)} = 1
        WHERE id IN ({placeholders})
        """,
        ids,
    )

    if cur.rowcount != EXPECTED_TRUE:
        raise RuntimeError(
            f"Lệnh UPDATE TRUE tác động {cur.rowcount} dòng, "
            f"không phải {EXPECTED_TRUE}."
        )

    total = conn.execute("SELECT COUNT(*) FROM communes").fetchone()[0]
    true_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM communes
        WHERE COALESCE({quote_ident(FLAG_COLUMN)}, 0) = 1
        """
    ).fetchone()[0]
    false_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM communes
        WHERE COALESCE({quote_ident(FLAG_COLUMN)}, 0) = 0
        """
    ).fetchone()[0]

    return int(total), int(true_count), int(false_count)


def verify_post_update(
    conn: sqlite3.Connection,
    total: int,
    true_count: int,
    false_count: int,
) -> None:
    if total != EXPECTED_TOTAL:
        raise RuntimeError(f"Sau ghi, tổng communes={total}, không phải {EXPECTED_TOTAL}.")
    if true_count != EXPECTED_TRUE:
        raise RuntimeError(f"Sau ghi, TRUE={true_count}, không phải {EXPECTED_TRUE}.")
    if false_count != EXPECTED_FALSE:
        raise RuntimeError(f"Sau ghi, FALSE={false_count}, không phải {EXPECTED_FALSE}.")

    # Kiểm tra không có xã nào ngoài danh sách 51 bị TRUE.
    ids = [int(x["id"]) for x in SPECIAL_COMMUNES]
    placeholders = ",".join("?" for _ in ids)

    extra = conn.execute(
        f"""
        SELECT id, code, name
        FROM communes
        WHERE COALESCE({quote_ident(FLAG_COLUMN)}, 0) = 1
          AND id NOT IN ({placeholders})
        ORDER BY id
        """,
        ids,
    ).fetchall()

    if extra:
        raise RuntimeError(
            "Có xã ngoài danh sách 51 bị TRUE: "
            + "; ".join(f"{r[0]} - {r[2]}" for r in extra)
        )

    missing = conn.execute(
        f"""
        SELECT id, code, name
        FROM communes
        WHERE id IN ({placeholders})
          AND COALESCE({quote_ident(FLAG_COLUMN)}, 0) <> 1
        ORDER BY id
        """,
        ids,
    ).fetchall()

    if missing:
        raise RuntimeError(
            "Có xã trong danh sách 51 chưa được TRUE: "
            + "; ".join(f"{r[0]} - {r[2]}" for r in missing)
        )

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if str(integrity).lower() != "ok":
        raise RuntimeError(f"PRAGMA integrity_check sau cập nhật không đạt: {integrity}")

    fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_rows:
        raise RuntimeError(
            f"foreign_key_check phát hiện {len(fk_rows)} lỗi sau cập nhật."
        )


def print_true_list(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        f"""
        SELECT id, code, name
        FROM communes
        WHERE COALESCE({quote_ident(FLAG_COLUMN)}, 0) = 1
        ORDER BY id
        """
    ).fetchall()

    print()
    print("-" * 88)
    print("DANH SÁCH 51 XÃ ĐÃ ĐƯỢC GẮN is_special_difficulty_area = 1")
    print("-" * 88)
    for idx, row in enumerate(rows, start=1):
        print(f"{idx:02d}. ID={row[0]:>3} | Mã={row[1]} | {row[2]}")


def main() -> int:
    print("=" * 88)
    print("BÀI 13B-11.15.2.4.9.0.3")
    print("GHI CỜ is_special_difficulty_area CHO 51 XÃ ĐẶC BIỆT KHÓ KHĂN")
    print("=" * 88)
    print()

    try:
        validate_source_list()
        db_path = find_db()
        print(f"[OK] Database: {db_path}")

        # Kiểm tra trước khi backup/ghi.
        ro = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            verify_database_identity(ro)
        finally:
            ro.close()

        print("[OK] Database khớp đúng kết quả đối chiếu 51/51.")
        print("[INFO] Đang tạo backup an toàn...")

        backup_path = make_backup(db_path)
        print(f"[OK] Backup: {backup_path}")

        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")

            created = ensure_flag_column(conn)
            if created:
                print(f"[OK] Đã tạo cột communes.{FLAG_COLUMN}")
            else:
                print(f"[OK] Cột communes.{FLAG_COLUMN} đã tồn tại")

            total, true_count, false_count = update_flags(conn)
            verify_post_update(conn, total, true_count, false_count)

            conn.commit()

            print()
            print("=" * 88)
            print("CẬP NHẬT THÀNH CÔNG")
            print("=" * 88)
            print(f"Tổng xã/phường : {total}")
            print(f"TRUE            : {true_count}")
            print(f"FALSE           : {false_count}")
            print(f"Backup          : {backup_path}")
            print()
            print("KẾT LUẬN: ĐẠT ĐÚNG 51/51 XÃ ĐẶC BIỆT KHÓ KHĂN.")

            print_true_list(conn)

        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

        print()
        print("=" * 88)
        print("BÀI 4.9.0.3 HOÀN THÀNH.")
        print("BƯỚC TIẾP THEO: BÀI 4.9.1 - TỰ ĐỘNG KẾT LUẬN ĐẠT CHUẨN / MỨC ĐỘ.")
        print("=" * 88)
        return 0

    except Exception as exc:
        print()
        print("=" * 88)
        print("[LỖI] KHÔNG HOÀN THÀNH BÀI 4.9.0.3")
        print(str(exc))
        print("Nếu transaction đã bắt đầu thì dữ liệu đã được ROLLBACK.")
        print("Nếu backup đã tạo, backup vẫn được giữ nguyên.")
        print("=" * 88)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
