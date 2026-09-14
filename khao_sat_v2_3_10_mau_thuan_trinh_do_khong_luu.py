# -*- coding: utf-8 -*-
from pathlib import Path
import re
import sqlite3
from datetime import datetime

ROOT = Path(r"C:\PhoCap")
SURVEYS = ROOT / "app" / "routers" / "surveys.py"
TEMPLATE = ROOT / "app" / "templates" / "surveys" / "year_records.html"
DB = ROOT / "data" / "phocap.db"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / f"bao_cao_khao_sat_v2_3_10_{datetime.now():%Y%m%d_%H%M%S}.txt"

def read(p):
    return p.read_text(encoding="utf-8-sig", errors="replace")

def section(text, title, start_pat, end_pat=None):
    m = re.search(start_pat, text, re.I | re.S)
    if not m:
        return f"\n--- {title} ---\nKHÔNG TÌM THẤY\n"
    start = m.start()
    if end_pat:
        n = re.search(end_pat, text[m.end():], re.I | re.S)
        end = m.end() + n.end() if n else min(len(text), start + 6000)
    else:
        end = min(len(text), start + 6000)
    return f"\n--- {title} ---\n{text[start:end]}\n"

def snippets(text, tokens, radius=18):
    lines = text.splitlines()
    out = []
    seen = set()
    for token in tokens:
        for i, line in enumerate(lines):
            if token.lower() in line.lower():
                a = max(0, i-radius)
                b = min(len(lines), i+radius+1)
                key = (a,b)
                if key in seen:
                    continue
                seen.add(key)
                out.append(f"\n>>> TOKEN: {token} | dòng {i+1}\n")
                for j in range(a,b):
                    mark = ">>" if j == i else "  "
                    out.append(f"{mark} {j+1:05d}: {lines[j]}\n")
    return "".join(out)

def main():
    print("="*110)
    print("KHẢO SÁT V2.3.10 - KHÔNG LƯU DỮ LIỆU + MÂU THUẪN TRÌNH ĐỘ")
    print("="*110)
    print("CHỈ ĐỌC - KHÔNG SỬA SOURCE / DATABASE")

    for p in (SURVEYS, TEMPLATE, DB):
        if not p.exists():
            raise SystemExit(f"Thiếu: {p}")

    s = read(SURVEYS)
    t = read(TEMPLATE)

    report = []
    report.append("="*110 + "\n")
    report.append("KHẢO SÁT V2.3.10 - KHÔNG LƯU DỮ LIỆU + MÂU THUẪN TRÌNH ĐỘ\n")
    report.append("="*110 + "\n")
    report.append(f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}\n")
    report.append("CHỈ ĐỌC - KHÔNG SỬA SOURCE / DATABASE.\n")

    report.append("\nMỤC TIÊU:\n")
    report.append("1) Kiểm tra V2.3.9 có làm select Lớp 3/Lớp 5 bị disabled và không POST hay không.\n")
    report.append("2) Lấy chính xác option/code của Trình độ học vấn cao nhất.\n")
    report.append("3) Kiểm tra backend đang validate/lưu highest_completed_grade và education_attainment_level thế nào.\n")
    report.append("4) Kiểm tra bản ghi test batch=114, household=13, person=48, school_year_id=2.\n")

    report.append("\n" + "="*110 + "\nSOURCE: year_records.html\n" + "="*110 + "\n")
    report.append(f"Marker V2.3.9 UI: {'CÓ' if 'BAI_13B_12_V2_3_9_DERIVED_GRADE_UI_START' in t else 'KHÔNG'}\n")
    report.append(f"g3.disabled = true: {'CÓ' if 'g3.disabled = true' in t else 'KHÔNG'}\n")
    report.append(f"g5.disabled = true: {'CÓ' if 'g5.disabled = true' in t else 'KHÔNG'}\n")

    for field in ("highest_completed_grade", "education_attainment_level", "completed_grade_3", "completed_grade_5"):
        pat = rf'<select[^>]+id="{re.escape(field)}"[^>]*>.*?</select>'
        m = re.search(pat, t, re.I | re.S)
        report.append(f"\n--- SELECT {field} ---\n")
        report.append((m.group(0) if m else "KHÔNG TÌM THẤY") + "\n")

    report.append("\n--- JS/LOGIC LIÊN QUAN ---\n")
    report.append(snippets(
        t,
        [
            "function applyEducationInference",
            "BAI_13B_12_V2_3_9_DERIVED_GRADE_UI_START",
            "g3.disabled = true",
            "g5.disabled = true",
            "education_attainment_level",
            "Lưu thành viên cuối và hoàn thành hộ",
        ],
        radius=24,
    ))

    report.append("\n" + "="*110 + "\nSOURCE: surveys.py\n" + "="*110 + "\n")
    report.append(f"Marker V2.3.9 backend: {'CÓ' if 'BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START' in s else 'KHÔNG'}\n")
    report.append(snippets(
        s,
        [
            "def luu_theo_doi_nam_hoc",
            "highest_completed_grade",
            "education_attainment_level",
            "record.highest_completed_grade",
            "record.education_attainment_level",
            "completed_grade_3",
            "completed_grade_5",
            "errors.append",
            "BAI_13B_12_V2_3_GRADE_TO_XMC_START",
            "BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START",
            "finish_household",
        ],
        radius=28,
    ))

    report.append("\n" + "="*110 + "\nDATABASE\n" + "="*110 + "\n")
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        report.append(f"integrity_check: {integrity}\n")
        report.append(f"foreign_key_check: {len(fk)} lỗi\n")

        cols = [r["name"] for r in con.execute("PRAGMA table_info(survey_person_year_records)").fetchall()]
        important = [
            "id","survey_form_id","survey_person_id","school_year_id",
            "highest_completed_grade","education_attainment_level",
            "completed_grade_3","completed_grade_5","literacy_status",
            "learning_status","updated_at"
        ]
        use = [c for c in important if c in cols]

        if use:
            sql = f"""
            SELECT {", ".join(use)}
            FROM survey_person_year_records
            WHERE survey_person_id = 48
              AND school_year_id = 2
            ORDER BY id DESC
            """
            rows = con.execute(sql).fetchall()
            report.append("\nBẢN GHI person=48, school_year_id=2:\n")
            if not rows:
                report.append("KHÔNG CÓ BẢN GHI.\n")
            for row in rows:
                report.append(" - " + " | ".join(f"{k}={row[k]!r}" for k in use) + "\n")

        # Xác định phiếu household 13 / batch 114
        form_cols = [r["name"] for r in con.execute("PRAGMA table_info(survey_forms)").fetchall()]
        form_use = [c for c in ["id","survey_batch_id","household_id","status","survey_date","updated_at"] if c in form_cols]
        rows = con.execute(
            f"SELECT {', '.join(form_use)} FROM survey_forms WHERE survey_batch_id=114 AND household_id=13"
        ).fetchall()
        report.append("\nPHIẾU batch=114, household=13:\n")
        for row in rows:
            report.append(" - " + " | ".join(f"{k}={row[k]!r}" for k in form_use) + "\n")

        if "education_attainment_level" in cols:
            report.append("\nGIÁ TRỊ education_attainment_level ĐANG CÓ TRONG DB:\n")
            vals = con.execute("""
                SELECT education_attainment_level, COUNT(*) AS n
                FROM survey_person_year_records
                GROUP BY education_attainment_level
                ORDER BY n DESC, education_attainment_level
            """).fetchall()
            for r in vals:
                report.append(f" - {r['education_attainment_level']!r}: {r['n']}\n")
    finally:
        con.close()

    report.append("\n" + "="*110 + "\nKẾT LUẬN KỸ THUẬT CẦN KHÓA CHO V2.3.10\n" + "="*110 + "\n")
    report.append("- Không sửa dữ liệu trong bước khảo sát này.\n")
    report.append("- Dùng chính option/code hiện có để đồng bộ Lớp cao nhất ↔ Trình độ học vấn.\n")
    report.append("- Nếu select lớp 3/lớp 5 đang disabled, V2.3.10 phải sửa để giá trị vẫn được POST.\n")
    report.append("- Backend phải là lớp bảo vệ cuối, không chỉ dựa vào JavaScript.\n")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(report), encoding="utf-8-sig")
    print("ĐÃ TẠO BÁO CÁO:")
    print(OUT)
    print("\nHãy gửi file báo cáo này lại để tạo V2.3.10 chính thức.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
