from __future__ import annotations

import re
import sqlite3
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"

TARGET_BATCH_ID = 3
TARGET_SCHOOL_USERNAME = "truong_40413308"  # Trường MN Nghi Hải

KEYWORDS = (
    "giao-phieu-giao-vien",
    "Giao phiếu cho giáo viên",
    "Phân công giáo viên",
    "Giao lại",
    "Thêm người phối hợp",
    "Thu hồi giáo viên",
    "Thu hồi phân công",
    "gửi kết quả lên xã",
    "gui ket qua len xa",
)

def section(title: str) -> None:
    print()
    print("=" * 120)
    print(title)
    print("=" * 120)

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")

def print_matches(path: Path, text: str, keyword: str, context: int = 5) -> None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if keyword.lower() in line.lower():
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            print(f"\n--- {path.relative_to(PROJECT)} | keyword={keyword!r} | line {i+1} ---")
            for n in range(start, end):
                print(f"{n+1:5}: {lines[n]}")

def extract_route_block(text: str, route_fragment: str) -> str | None:
    lines = text.splitlines()
    hit = None
    for i, line in enumerate(lines):
        if "@router." in line and route_fragment in line:
            hit = i
            break
    if hit is None:
        return None

    start = hit
    while start > 0 and lines[start - 1].lstrip().startswith("@"):
        start -= 1

    end = len(lines)
    for j in range(hit + 1, len(lines)):
        if lines[j].startswith("@router."):
            end = j
            break
    return "\n".join(f"{n+1:5}: {lines[n]}" for n in range(start, end))

def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in con.execute(f'PRAGMA table_info("{table}")').fetchall()]

def print_rows(rows) -> None:
    if not rows:
        print("(không có)")
        return
    for row in rows:
        print(" | ".join(f"{k}={row[k]}" for k in row.keys()))

def main() -> None:
    print("KIỂM TRA BÀI 13B-10 V3.12 - GIAO PHIẾU TỪ TRƯỜNG CHO GIÁO VIÊN")
    print("CHỈ ĐỌC - KHÔNG SỬA SOURCE / DATABASE")
    print(f"Project: {PROJECT}")
    print(f"Database: {DB}")

    section("1. TÌM ROUTE / TEMPLATE LIÊN QUAN")
    for folder, pattern in (
        (APP / "routers", "*.py"),
        (APP / "templates", "*.html"),
    ):
        if not folder.exists():
            continue
        for path in folder.rglob(pattern):
            text = read_text(path)
            if any(k.lower() in text.lower() for k in KEYWORDS):
                print(f"\nFILE: {path.relative_to(PROJECT)}")
                for keyword in KEYWORDS:
                    if keyword.lower() in text.lower():
                        print_matches(path, text, keyword, context=3)

    section("2. NGUYÊN KHỐI ROUTE GIAO PHIẾU CHO GIÁO VIÊN")
    found_route = False
    for path in (APP / "routers").rglob("*.py"):
        text = read_text(path)
        if "giao-phieu-giao-vien" in text:
            block = extract_route_block(text, "giao-phieu-giao-vien")
            if block:
                print(f"\nFILE: {path.relative_to(PROJECT)}")
                print(block)
                found_route = True
    if not found_route:
        print("Không tìm thấy decorator route chứa 'giao-phieu-giao-vien'.")

    section("3. NGUYÊN KHỐI ROUTE PHÂN CÔNG TỪNG PHIẾU")
    found_assign = False
    for path in (APP / "routers").rglob("*.py"):
        text = read_text(path)
        # In các route có /phan-cong và ho-dan
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "@router." in line and "phan-cong" in line and "ho-dan" in line:
                start = i
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("@router."):
                        end = j
                        break
                print(f"\nFILE: {path.relative_to(PROJECT)} | line {i+1}")
                for n in range(start, end):
                    print(f"{n+1:5}: {lines[n]}")
                found_assign = True
    if not found_assign:
        print("Không tìm thấy route /ho-dan/.../phan-cong.")

    if not DB.exists():
        section("4. DATABASE")
        print("Không tìm thấy database.")
        return

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    try:
        section("4. CÁC BẢNG CÓ THỂ LIÊN QUAN ĐẾN GIAO / PHÂN CÔNG / NHẬT KÝ")
        tables = [
            row["name"]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        relevant = [
            t for t in tables
            if any(
                token in t.lower()
                for token in (
                    "survey",
                    "assign",
                    "investigator",
                    "handoff",
                    "delivery",
                    "dispatch",
                    "log",
                    "audit",
                    "history",
                )
            )
        ]
        for table in relevant:
            print(f"{table}: {table_columns(con, table)}")

        section("5. TÀI KHOẢN TRƯỜNG TEST")
        school_row = con.execute(
            """
            SELECT
                u.id AS user_id,
                u.username,
                u.full_name,
                u.school_id,
                u.commune_id,
                u.is_active,
                s.code AS school_code,
                s.name AS school_name
            FROM users u
            LEFT JOIN schools s ON s.id = u.school_id
            WHERE u.username = ?
            """,
            (TARGET_SCHOOL_USERNAME,),
        ).fetchone()
        if school_row:
            print_rows([school_row])
            school_id = school_row["school_id"]
        else:
            print(f"Không tìm thấy {TARGET_SCHOOL_USERNAME}")
            school_id = None

        section("6. PHIẾU ĐỢT #3 MÀ TRƯỜNG CÓ GIÁO VIÊN TRONG TỔ")
        if school_id is not None:
            rows = con.execute(
                """
                SELECT DISTINCT
                    sf.id AS form_id,
                    sf.form_number,
                    sf.household_id
                FROM survey_forms sf
                JOIN survey_form_investigators sfi
                  ON sfi.survey_form_id = sf.id
                JOIN users u
                  ON u.id = sfi.user_id
                WHERE sf.survey_batch_id = ?
                  AND u.school_id = ?
                ORDER BY sf.id
                """,
                (TARGET_BATCH_ID, int(school_id)),
            ).fetchall()
            print_rows(rows)
            print(f"Tổng: {len(rows)} phiếu")
        else:
            print("(bỏ qua do chưa xác định school_id)")

        section("7. TOÀN BỘ 3 NGƯỜI ĐANG ĐƯỢC PHÂN CÔNG TRÊN TỪNG PHIẾU")
        if school_id is not None:
            rows = con.execute(
                """
                SELECT
                    sf.id AS form_id,
                    sf.form_number,
                    sfi.order_number,
                    sfi.is_primary,
                    u.id AS user_id,
                    u.username,
                    u.full_name,
                    u.school_id,
                    s.name AS school_name,
                    r.code AS role_code,
                    sfi.signed_at,
                    sfi.notes
                FROM survey_forms sf
                JOIN survey_form_investigators sfi
                  ON sfi.survey_form_id = sf.id
                JOIN users u
                  ON u.id = sfi.user_id
                LEFT JOIN schools s
                  ON s.id = u.school_id
                LEFT JOIN roles r
                  ON r.id = u.role_id
                WHERE sf.survey_batch_id = ?
                  AND sf.id IN (
                      SELECT DISTINCT sf2.id
                      FROM survey_forms sf2
                      JOIN survey_form_investigators sfi2
                        ON sfi2.survey_form_id = sf2.id
                      JOIN users u2
                        ON u2.id = sfi2.user_id
                      WHERE sf2.survey_batch_id = ?
                        AND u2.school_id = ?
                  )
                ORDER BY sf.id, sfi.order_number, sfi.id
                """,
                (TARGET_BATCH_ID, TARGET_BATCH_ID, int(school_id)),
            ).fetchall()
            print_rows(rows)

        section("8. KIỂM TRA BẢNG survey_school_assignments")
        if "survey_school_assignments" in tables and school_id is not None:
            cols = table_columns(con, "survey_school_assignments")
            print("Columns:", cols)
            if "survey_batch_id" in cols and "school_id" in cols:
                rows = con.execute(
                    """
                    SELECT *
                    FROM survey_school_assignments
                    WHERE survey_batch_id = ?
                      AND school_id = ?
                    """,
                    (TARGET_BATCH_ID, int(school_id)),
                ).fetchall()
                print_rows(rows)
            else:
                print("Bảng không có bộ cột survey_batch_id + school_id.")
        else:
            print("(không có bảng hoặc chưa xác định school_id)")

        section("9. TÌM BẢNG CÓ CỘT TRẠNG THÁI / THỜI GIAN / NGƯỜI GỬI")
        for table in relevant:
            cols = table_columns(con, table)
            interesting = [
                c for c in cols
                if any(
                    token in c.lower()
                    for token in (
                        "status",
                        "sent",
                        "send",
                        "submitted",
                        "confirmed",
                        "signed",
                        "assigned",
                        "updated_by",
                        "created_by",
                        "school_id",
                        "survey_form_id",
                        "survey_batch_id",
                    )
                )
            ]
            if interesting:
                print(f"{table}: {interesting}")

        section("10. KẾT LUẬN")
        print("Script đã thu thập:")
        print("- Route trang Giao phiếu cho giáo viên.")
        print("- Route điều chỉnh phân công từng phiếu.")
        print("- Template/chuỗi giao diện liên quan.")
        print("- Schema các bảng phân công/nhật ký hiện có.")
        print("- Các phiếu đợt #3 thuộc phạm vi Trường MN Nghi Hải.")
        print("- Đủ 3 người đang phân công trên từng phiếu.")
        print()
        print("KHÔNG CÓ INSERT / UPDATE / DELETE.")

    finally:
        con.close()

if __name__ == "__main__":
    main()
