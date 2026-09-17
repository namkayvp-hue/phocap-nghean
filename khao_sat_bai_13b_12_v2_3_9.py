# -*- coding: utf-8 -*-
from pathlib import Path
from datetime import datetime
import sqlite3, re

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"bao_cao_khao_sat_v2_3_9_{STAMP}.txt"

FILES = [
    APP / "routers" / "surveys.py",
    APP / "templates" / "surveys" / "year_records.html",
    APP / "templates" / "surveys" / "households.html",
]
KEYWORDS = [
    "highest_completed_grade", "completed_grade_3", "completed_grade_5",
    "literacy_status", "is_literacy_target", "Hộ gia đình đã xác nhận",
    "Người đại diện hộ", "Ngày điều tra", "Trạng thái phiếu",
    "hoàn thành phiếu", "Lưu thành viên cuối", "year_record_saved",
    "phieu/cap-nhat", "cap-nhat"
]

def read_text(p):
    return p.read_text(encoding="utf-8-sig", errors="replace")

def add_hits(report, p):
    report += ["", "-"*110, f"FILE: {p}"]
    if not p.exists():
        report.append("KHÔNG TỒN TẠI")
        return
    lines = read_text(p).splitlines()
    hits = []
    for i, line in enumerate(lines, 1):
        low = line.casefold()
        if any(k.casefold() in low for k in KEYWORDS):
            hits.append(i)
    report.append(f"Số dòng khớp: {len(hits)}")
    for pos in hits[:80]:
        a = max(1, pos-5); b = min(len(lines), pos+8)
        for i in range(a, b+1):
            report.append(f"{'>>' if i==pos else '  '} {i:05d}: {lines[i-1]}")
        report.append("")

def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    report = [
        "="*110,
        "KHẢO SÁT V2.3.9 - ĐỒNG BỘ TRÌNH ĐỘ + HOÀN THÀNH HỘ TỰ ĐỘNG",
        "="*110,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "CHỈ ĐỌC - KHÔNG SỬA SOURCE / DATABASE.",
        "",
        "MỤC TIÊU:",
        "1) Lớp cao nhất đã hoàn thành là dữ liệu gốc.",
        "2) Hoàn thành lớp 3/lớp 5 được suy ra để tránh mâu thuẫn XMC.",
        "3) Lưu thành viên cuối và hoàn thành hộ trong một thao tác.",
        "4) Tự điền người đại diện = chủ hộ, ngày điều tra nếu trống, trạng thái Đã hoàn thành.",
        "5) Giữ nguyên quy tắc PCGD/XMC hiện có.",
    ]

    for p in FILES:
        add_hits(report, p)

    report += ["", "="*110, "DATABASE", "="*110]

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        report.append(f"integrity_check: {integrity}")
        report.append(f"foreign_key_check: {len(fk)} lỗi")

        for table in ("survey_forms","survey_person_year_records","households"):
            report += ["", f"CỘT QUAN TRỌNG BẢNG {table}:"]
            try:
                cols = con.execute(f'PRAGMA table_info("{table}")').fetchall()
                for c in cols:
                    name = str(c["name"])
                    if any(t in name.casefold() for t in (
                        "status","confirm","represent","head","survey","date",
                        "grade","literacy","complete","review"
                    )):
                        report.append(f" - {name} | {c['type']} | default={c['dflt_value']}")
            except Exception as e:
                report.append(f" - lỗi: {e}")

        report += ["", "TRẠNG THÁI PHIẾU:"]
        try:
            for r in con.execute(
                "SELECT status, COUNT(*) total FROM survey_forms GROUP BY status ORDER BY total DESC"
            ).fetchall():
                report.append(f" - {r['status']}: {r['total']}")
        except Exception as e:
            report.append(f" - lỗi: {e}")

        report += ["", "MÂU THUẪN LỚP CAO NHẤT ↔ HOÀN THÀNH LỚP 3/5:"]
        try:
            rows = con.execute(
                """
                SELECT spr.id, spr.survey_person_id, sp.full_name, spr.school_year_id,
                       spr.highest_completed_grade, spr.completed_grade_3, spr.completed_grade_5,
                       spr.is_literacy_target, spr.literacy_status
                FROM survey_person_year_records spr
                JOIN survey_people sp ON sp.id = spr.survey_person_id
                WHERE
                    (spr.completed_grade_3 = 1 AND COALESCE(spr.highest_completed_grade,0) < 3)
                 OR (spr.completed_grade_5 = 1 AND COALESCE(spr.highest_completed_grade,0) < 5)
                 OR (spr.completed_grade_3 = 0 AND COALESCE(spr.highest_completed_grade,0) >= 3)
                 OR (spr.completed_grade_5 = 0 AND COALESCE(spr.highest_completed_grade,0) >= 5)
                ORDER BY spr.id
                LIMIT 100
                """
            ).fetchall()
            report.append(f" - Số bản ghi mâu thuẫn: {len(rows)}")
            for r in rows:
                report.append("   " + " | ".join(f"{k}={r[k]}" for k in r.keys()))
        except Exception as e:
            report.append(f" - lỗi: {e}")

        report += ["", "PHIẾU TEST batch=114, household=13 (nếu có):"]
        try:
            row = con.execute(
                "SELECT * FROM survey_forms WHERE survey_batch_id=114 AND household_id=13 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                for k in row.keys():
                    report.append(f" - {k}: {row[k]}")
            else:
                report.append(" - Không tìm thấy.")
        except Exception as e:
            report.append(f" - lỗi: {e}")
    finally:
        con.close()

    report += [
        "", "="*110, "KẾT LUẬN DÙNG CHO BỘ CÀI V2.3.9", "="*110,
        "Báo cáo này dùng để khóa chính xác route lưu year-record, route hoàn thành phiếu,",
        "các trường xác nhận hộ/người đại diện/ngày điều tra/trạng thái và dữ liệu mâu thuẫn hiện có.",
        "Sau đó mới tạo V2.3.9 chính thức để không đụng nhầm các luồng đã ổn."
    ]

    REPORT.write_text("\n".join(report)+"\n", encoding="utf-8-sig")
    print("="*110)
    print("KHẢO SÁT V2.3.9 HOÀN THÀNH - KHÔNG THAY ĐỔI DỮ LIỆU")
    print("="*110)
    print("Báo cáo:", REPORT)

if __name__ == "__main__":
    main()
