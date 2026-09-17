from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
EXPORTS = PROJECT / "exports"
ROUTER = PROJECT / "app" / "routers" / "surveys.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"bao_cao_bai_13b_12_0_khao_sat_nguon_ho_dan_{STAMP}.txt"

KEYWORDS = (
    "survey", "house", "household", "family", "person", "member",
    "ho_", "ho", "phieu", "doi_tuong", "doituong", "thanh_vien",
    "school_year", "commune", "batch"
)

SOURCE_KEYWORDS = (
    "chuyen_nam", "chuyển năm", "nam_truoc", "năm trước",
    "rollover", "copy", "sao_chep", "sao chép",
    "SurveyForm", "SurveyBatch", "Household", "Person",
    "household", "survey_form", "tao_phieu", "tạo phiếu"
)


def emit(lines: list[str], text: str = "") -> None:
    print(text)
    lines.append(text)


def find_database() -> Path:
    preferred = [
        PROJECT / "phocap.db",
        PROJECT / "data" / "phocap.db",
        PROJECT / "app" / "phocap.db",
    ]
    for p in preferred:
        if p.exists() and p.is_file():
            return p

    found: list[Path] = []
    for p in PROJECT.rglob("*.db"):
        s = str(p).lower()
        if any(x in s for x in ("\\.venv\\", "/.venv/", "\\exports\\", "/exports/",
                                 "\\backup", "/backup")):
            continue
        if p.is_file():
            found.append(p)

    if not found:
        raise RuntimeError("Không tìm thấy tệp database .db trong C:\\PhoCap.")

    found.sort(key=lambda p: p.stat().st_size, reverse=True)
    return found[0]


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_info(conn: sqlite3.Connection, table: str):
    return conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()


def foreign_keys(conn: sqlite3.Connection, table: str):
    return conn.execute(f"PRAGMA foreign_key_list({qident(table)})").fetchall()


def row_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {qident(table)}").fetchone()[0])


def safe_distinct_counts(conn: sqlite3.Connection, table: str, col: str, limit: int = 30):
    sql = (
        f"SELECT {qident(col)}, COUNT(*) "
        f"FROM {qident(table)} "
        f"GROUP BY {qident(col)} "
        f"ORDER BY COUNT(*) DESC LIMIT ?"
    )
    return conn.execute(sql, (limit,)).fetchall()


def relevant_table(table: str, columns: list[str]) -> bool:
    hay = (table + " " + " ".join(columns)).lower()
    special_cols = {
        "survey_batch_id", "school_year_id", "commune_id",
        "household_id", "survey_form_id", "person_id"
    }
    if special_cols.intersection({c.lower() for c in columns}):
        return True
    return any(k in hay for k in KEYWORDS)


def source_scan(lines: list[str]) -> None:
    emit(lines)
    emit(lines, "=" * 108)
    emit(lines, "5. KHẢO SÁT SOURCE app/routers/surveys.py")
    emit(lines, "=" * 108)

    if not ROUTER.exists():
        emit(lines, f"Không tìm thấy: {ROUTER}")
        return

    text_lines = ROUTER.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    hits = []
    for i, line in enumerate(text_lines, start=1):
        low = line.lower()
        if any(k.lower() in low for k in SOURCE_KEYWORDS):
            hits.append((i, line.rstrip()))

    emit(lines, f"Số dòng khớp từ khóa nghiệp vụ: {len(hits)}")
    for i, line in hits[:160]:
        emit(lines, f"{i:5d}: {line}")

    if len(hits) > 160:
        emit(lines, f"... còn {len(hits) - 160} dòng khớp khác, đã lược bớt để báo cáo gọn.")


def main() -> int:
    lines: list[str] = []

    emit(lines, "=" * 108)
    emit(lines, "BÀI 13B-12.0 - KHẢO SÁT NGUỒN DỮ LIỆU HỘ DÂN CHO ĐỢT ĐIỀU TRA MỚI")
    emit(lines, "=" * 108)
    emit(lines)
    emit(lines, "MỤC TIÊU:")
    emit(lines, " - Xác định chính xác bảng hộ dân, thành viên, phiếu điều tra, đợt và năm học.")
    emit(lines, " - Kiểm tra dữ liệu năm trước còn hay không.")
    emit(lines, " - Kiểm tra đợt mới đã có phiếu/hộ hay chưa.")
    emit(lines, " - Tìm chức năng chuyển năm/sao chép đã có trong source để không làm trùng.")
    emit(lines)
    emit(lines, "AN TOÀN:")
    emit(lines, " - Chỉ mở SQLite ở chế độ READ-ONLY.")
    emit(lines, " - KHÔNG INSERT / UPDATE / DELETE.")
    emit(lines, " - KHÔNG sửa source.")
    emit(lines, " - KHÔNG đổi menu/giao diện/phân quyền.")
    emit(lines)

    db_path = find_database()
    emit(lines, f"Database được chọn: {db_path}")
    emit(lines, f"Dung lượng: {db_path.stat().st_size:,} bytes")

    uri = db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row

    try:
        emit(lines)
        emit(lines, "=" * 108)
        emit(lines, "1. KIỂM TRA SQLITE")
        emit(lines, "=" * 108)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        emit(lines, f"integrity_check = {integrity}")
        emit(lines, f"foreign_key_check = {len(fk_rows)} lỗi")

        tables = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
        ]

        emit(lines)
        emit(lines, "=" * 108)
        emit(lines, "2. DANH SÁCH BẢNG LIÊN QUAN")
        emit(lines, "=" * 108)

        candidates = []
        for table in tables:
            info = table_info(conn, table)
            cols = [r["name"] for r in info]
            if relevant_table(table, cols):
                candidates.append((table, cols))

        emit(lines, f"Tổng số bảng trong DB: {len(tables)}")
        emit(lines, f"Số bảng được nhận diện có liên quan: {len(candidates)}")

        for table, cols in candidates:
            try:
                n = row_count(conn, table)
            except Exception as exc:
                n = f"LỖI ĐẾM: {exc}"
            emit(lines)
            emit(lines, f"[{table}]  rows={n}")
            emit(lines, "  columns: " + ", ".join(cols))
            fks = foreign_keys(conn, table)
            if fks:
                emit(lines, "  foreign keys:")
                for fk in fks:
                    emit(
                        lines,
                        f"    {fk['from']} -> {fk['table']}.{fk['to']}"
                    )

        emit(lines)
        emit(lines, "=" * 108)
        emit(lines, "3. PHÂN BỐ DỮ LIỆU THEO KHÓA NGHIỆP VỤ")
        emit(lines, "=" * 108)

        interesting_cols = (
            "school_year_id", "commune_id", "survey_batch_id",
            "household_id", "survey_form_id", "status"
        )

        for table, cols in candidates:
            lower_map = {c.lower(): c for c in cols}
            selected = [lower_map[c] for c in interesting_cols if c in lower_map]
            if not selected:
                continue

            emit(lines)
            emit(lines, f"[{table}]")
            for col in selected:
                try:
                    rows = safe_distinct_counts(conn, table, col)
                    preview = ", ".join(
                        f"{r[0]!r}:{r[1]}" for r in rows[:20]
                    )
                    emit(lines, f"  {col}: {preview}")
                except Exception as exc:
                    emit(lines, f"  {col}: LỖI {exc}")

        emit(lines)
        emit(lines, "=" * 108)
        emit(lines, "4. TÌM CÁC BẢNG CÓ THỂ LÀ DỮ LIỆU HỘ / THÀNH VIÊN / PHIẾU")
        emit(lines, "=" * 108)

        priority = []
        for table, cols in candidates:
            low_t = table.lower()
            low_cols = {c.lower() for c in cols}
            score = 0
            if "house" in low_t or "ho_" in low_t or low_t.startswith("ho"):
                score += 5
            if "person" in low_t or "member" in low_t or "doi_tuong" in low_t:
                score += 5
            if "form" in low_t or "phieu" in low_t:
                score += 5
            for c in ("household_id", "survey_batch_id", "survey_form_id", "person_id"):
                if c in low_cols:
                    score += 3
            if score:
                priority.append((score, table, cols))

        priority.sort(reverse=True)
        for score, table, cols in priority:
            emit(lines, f"score={score:02d}  {table}: {', '.join(cols)}")

        source_scan(lines)

        emit(lines)
        emit(lines, "=" * 108)
        emit(lines, "KẾT LUẬN BƯỚC 13B-12.0")
        emit(lines, "=" * 108)
        emit(lines, "Khảo sát hoàn tất. Không có dữ liệu nào bị thay đổi.")
        emit(lines, "Hãy gửi toàn bộ kết quả PowerShell hoặc tệp báo cáo trong exports để xây Bài 13B-12.1.")

    finally:
        conn.close()

    EXPORTS.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print("Báo cáo đã lưu:")
    print(REPORT)
    print()
    print("BÀI 13B-12.0 HOÀN THÀNH - DATABASE VÀ SOURCE KHÔNG BỊ THAY ĐỔI")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 108)
        print("BÀI 13B-12.0 DỪNG AN TOÀN")
        print("=" * 108)
        print(type(exc).__name__ + ":", exc)
        print("Không có thao tác ghi database hoặc sửa source nào được thực hiện.")
        raise
