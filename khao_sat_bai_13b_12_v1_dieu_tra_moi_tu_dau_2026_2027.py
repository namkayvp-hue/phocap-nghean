# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

FILES = [
    APP / "templates" / "partials" / "dropdown_menu_v1.html",
    APP / "routers" / "surveys.py",
    APP / "routers" / "survey_print.py",
    APP / "routers" / "household_updates.py",
    APP / "access_control.py",
    APP / "models.py",
]

KEYWORDS = [
    "Cập nhật dữ liệu hộ dân",
    "cap-nhat-ho-dan",
    "Nhập Excel cập nhật hộ dân",
    "Danh sách hộ dân / phiếu được giao",
    "In phiếu điều tra",
    "thêm hộ",
    "tạo hộ",
    "hộ dân mới",
    "household",
    "survey_form",
    "SurveyForm",
    "SurveyPerson",
    "SurveyPersonYearRecord",
    "commune_id",
    "school_id",
    "classroom_id",
    "school_year_id",
]


def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1258"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            pass
    return ""


def context_hits(path: Path):
    text = read_text(path)
    if not text:
        return []
    lines = text.splitlines()
    hits = []
    seen = set()
    for i, line in enumerate(lines, 1):
        low = line.lower()
        if any(k.lower() in low for k in KEYWORDS):
            start = max(1, i - 4)
            end = min(len(lines), i + 6)
            key = (start, end)
            if key in seen:
                continue
            seen.add(key)
            block = [f"{n:05d}: {lines[n-1]}" for n in range(start, end + 1)]
            hits.append((i, block))
    return hits


def table_exists(con, table):
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def safe_count(con, sql, params=()):
    try:
        return con.execute(sql, params).fetchone()[0]
    except Exception as exc:
        return f"ERROR: {exc}"


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = EXPORTS / (
        "bao_cao_khao_sat_bai_13b_12_"
        f"dieu_tra_moi_tu_dau_{stamp}.txt"
    )

    lines = []
    lines.append("=" * 118)
    lines.append(
        "KHẢO SÁT BÀI 13B-12 V1 - "
        "ĐIỀU TRA MỚI TỪ ĐẦU NĂM HỌC 2026-2027"
    )
    lines.append("=" * 118)
    lines.append(f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}")
    lines.append(f"Dự án: {PROJECT}")
    lines.append("")
    lines.append("MỤC TIÊU KHẢO SÁT:")
    lines.append(
        "1. Ẩn/khóa chức năng 'Cập nhật dữ liệu hộ dân' đối với tài khoản Xã, "
        "nhưng không xóa code/dữ liệu cũ."
    )
    lines.append(
        "2. Bổ sung 'Nhập hồ sơ hộ dân mới' cho điều tra mới từ đầu 2026-2027."
    )
    lines.append(
        "3. Tạo phiếu điều tra mới không kế thừa địa chỉ/trường cũ; "
        "dùng danh mục hiện tại sau sáp nhập."
    )
    lines.append(
        "4. Dữ liệu học sinh 2025-2026 chỉ dùng làm dự kiến liên năm/đối chiếu, "
        "không tạo dữ liệu điều tra 2026-2027."
    )
    lines.append("")

    lines.append("I. KIỂM TRA CÁC FILE LIÊN QUAN")
    for path in FILES:
        lines.append("")
        lines.append(f"[FILE] {path}")
        if not path.is_file():
            lines.append("  KHÔNG TỒN TẠI")
            continue
        lines.append(f"  Kích thước: {path.stat().st_size} bytes")
        hits = context_hits(path)
        lines.append(f"  Khối khớp từ khóa: {len(hits)}")
        for _, block in hits[:40]:
            lines.append("  ---")
            lines.extend("  " + x for x in block)
        if len(hits) > 40:
            lines.append(f"  ... còn {len(hits)-40} khối không in.")
    lines.append("")

    if not DB.is_file():
        lines.append("II. DATABASE: KHÔNG TÌM THẤY")
    else:
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = len(con.execute("PRAGMA foreign_key_check").fetchall())
            lines.append("II. DATABASE")
            lines.append(f"integrity_check: {integrity}")
            lines.append(f"foreign_key_check: {fk} lỗi")
            lines.append("")

            tables = [
                r["name"]
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

            interesting = [
                t for t in tables
                if any(
                    s in t.lower()
                    for s in (
                        "survey", "house", "person",
                        "school_year", "school",
                        "commune", "class"
                    )
                )
            ]

            lines.append("III. CÁC BẢNG LIÊN QUAN")
            for table in interesting:
                lines.append("")
                lines.append(f"[{table}]")
                cols = con.execute(f'PRAGMA table_info("{table}")').fetchall()
                for c in cols:
                    lines.append(
                        f"  - {c['name']} | {c['type']} | "
                        f"notnull={c['notnull']} | pk={c['pk']}"
                    )
                count = safe_count(con, f'SELECT COUNT(*) FROM "{table}"')
                lines.append(f"  Số bản ghi: {count}")

            lines.append("")
            lines.append("IV. DỮ LIỆU THEO NĂM HỌC / ĐỢT ĐIỀU TRA")

            if table_exists(con, "school_years"):
                years = con.execute(
                    "SELECT id, code, is_active FROM school_years ORDER BY code"
                ).fetchall()
                for y in years:
                    lines.append(
                        f"school_year: id={y['id']} "
                        f"code={y['code']} active={y['is_active']}"
                    )

            if (
                table_exists(con, "survey_batches")
                and table_exists(con, "school_years")
            ):
                rows = con.execute(
                    """
                    SELECT sy.code AS school_year, COUNT(*) AS batch_count
                    FROM survey_batches sb
                    JOIN school_years sy ON sy.id = sb.school_year_id
                    GROUP BY sy.code
                    ORDER BY sy.code
                    """
                ).fetchall()
                for r in rows:
                    lines.append(
                        f"survey_batches {r['school_year']}: {r['batch_count']}"
                    )

            if (
                table_exists(con, "survey_forms")
                and table_exists(con, "survey_batches")
                and table_exists(con, "school_years")
            ):
                rows = con.execute(
                    """
                    SELECT sy.code AS school_year, COUNT(sf.id) AS form_count
                    FROM survey_forms sf
                    JOIN survey_batches sb ON sb.id = sf.survey_batch_id
                    JOIN school_years sy ON sy.id = sb.school_year_id
                    GROUP BY sy.code
                    ORDER BY sy.code
                    """
                ).fetchall()
                for r in rows:
                    lines.append(
                        f"survey_forms {r['school_year']}: {r['form_count']}"
                    )

            lines.append("")
            lines.append("V. KIỂM TRA DỮ LIỆU 2026-2027 HIỆN CÓ")
            if (
                table_exists(con, "survey_forms")
                and table_exists(con, "survey_batches")
                and table_exists(con, "school_years")
            ):
                count = safe_count(
                    con,
                    """
                    SELECT COUNT(sf.id)
                    FROM survey_forms sf
                    JOIN survey_batches sb ON sb.id = sf.survey_batch_id
                    JOIN school_years sy ON sy.id = sb.school_year_id
                    WHERE sy.code = '2026-2027'
                    """
                )
                lines.append("Số phiếu 2026-2027 hiện có: " + str(count))
                lines.append(
                    "LƯU Ý: khảo sát chỉ báo số lượng; "
                    "KHÔNG xóa/đổi dữ liệu thử nghiệm hiện có."
                )
        finally:
            con.close()

    lines.append("")
    lines.append("VI. NGUYÊN TẮC BỘ CÀI TIẾP THEO")
    lines.append(
        "- Chỉ ẨN menu + chặn route Cập nhật dữ liệu hộ dân đối với role XA; "
        "không xóa route, template hay dữ liệu."
    )
    lines.append(
        "- Thêm chức năng mới, không đổi tên/xóa các chức năng 2.2.x đang chạy."
    )
    lines.append(
        "- Hồ sơ hộ mới ghi trực tiếp vào đợt 2026-2027 hiện hành của đúng xã."
    )
    lines.append(
        "- Địa chỉ, thôn/xóm, trường/lớp lấy theo danh mục hiện tại; "
        "không tự chép từ dữ liệu 2025-2026."
    )
    lines.append(
        "- Dữ liệu học sinh 2025-2026 chỉ là nguồn tham chiếu liên năm, "
        "không ghi đè dữ liệu điều tra 2026-2027."
    )
    lines.append(
        "- Từ 2027-2028 trở đi mới dùng dữ liệu điều tra đã xác nhận của năm trước "
        "làm nền liên năm."
    )
    lines.append("")
    lines.append(
        "KHẢO SÁT CHỈ ĐỌC - KHÔNG THAY ĐỔI MÃ NGUỒN HOẶC DATABASE."
    )

    report.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    print("=" * 118)
    print("KHẢO SÁT HOÀN TẤT - KHÔNG THAY ĐỔI SOURCE/DATABASE")
    print("=" * 118)
    print("Báo cáo:", report)
    print("Hãy gửi file báo cáo này để tạo bộ cài an toàn.")


if __name__ == "__main__":
    main()
