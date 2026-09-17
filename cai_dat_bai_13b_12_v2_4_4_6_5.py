from __future__ import annotations

import py_compile
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
SURVEYS = ROOT / "app" / "routers" / "surveys.py"
TEMPLATE = ROOT / "app" / "templates" / "surveys" / "summary_report.html"
MARKER = "BAI_13B_12_V2_4_4_6_5_SUMMARY_ACTIVE_INDICATORS"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Khong tim thay dung 1 vi tri de sua [{label}] (tim thay {count}).")
    return text.replace(old, new, 1)


def main() -> int:
    print("BAI 13B-12 V2.4.4.6.5 - BAO CAO TONG HOP DOT")
    print("- Sua loi Internal Server Error /bao-cao-tong-hop.")
    print("- Chi giu cac chi bao dang thuc su theo doi trong bao cao.")
    print("- An chi bao cu khoi giao dien va file Excel, khong xoa du lieu DB.")
    print("- Khong sua database, menu, mobile hay cac bao cao MN/TH/THCS/XMC.\n")

    if not SURVEYS.exists() or not TEMPLATE.exists():
        raise FileNotFoundError("Khong tim thay surveys.py hoac summary_report.html trong C:\\PhoCap")

    s = SURVEYS.read_text(encoding="utf-8")
    t = TEMPLATE.read_text(encoding="utf-8")

    if MARKER in s:
        print("[THONG BAO] V2.4.4.6.5 da duoc cai truoc do. Khong sua lap.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / "backups" / f"backup_bai_13b_12_v2_4_4_6_5_{stamp}"
    (backup_dir / "app" / "routers").mkdir(parents=True, exist_ok=True)
    (backup_dir / "app" / "templates" / "surveys").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SURVEYS, backup_dir / "app" / "routers" / "surveys.py")
    shutil.copy2(TEMPLATE, backup_dir / "app" / "templates" / "surveys" / "summary_report.html")
    print(f"[BACKUP] {backup_dir}")

    try:
        old_select = '''            SurveyPersonYearRecord.completed_preschool_5.label(\n                "completed_preschool_5"\n            ),\n            SurveyPersonYearRecord.attends_required_days.label(\n                "attends_required_days"\n            ),\n            SurveyPersonYearRecord.attends_regularly.label(\n                "attends_regularly"\n            ),\n            SurveyPersonYearRecord.prepared_vietnamese.label(\n                "prepared_vietnamese"\n            ),\n            SurveyPersonYearRecord.weight_monitored.label(\n                "weight_monitored"\n            ),\n            SurveyPersonYearRecord.underweight.label("underweight"),\n            SurveyPersonYearRecord.height_monitored.label(\n                "height_monitored"\n            ),\n            SurveyPersonYearRecord.stunted.label("stunted"),\n'''
        new_select = f'''            # === {MARKER} ===\n            # Bao cao tong hop chi lay cac chi bao dang con theo doi.\n            SurveyPersonYearRecord.completed_preschool_by_age.label(\n                "completed_preschool_by_age"\n            ),\n            SurveyPersonYearRecord.attends_two_sessions_per_day.label(\n                "attends_two_sessions_per_day"\n            ),\n            SurveyPersonYearRecord.prepared_vietnamese.label(\n                "prepared_vietnamese"\n            ),\n'''
        s = replace_once(s, old_select, new_select, "query chi bao")

        old_labels = '''    indicator_labels = {\n        "completed_preschool_by_age": "Hoàn thành Chương trình GDMN theo độ tuổi",\n        "completed_preschool_5": "Hoàn thành chương trình mầm non 5 tuổi (dữ liệu cũ)",\n        "attends_required_days": "Đi học đủ ngày theo quy định",\n        "attends_regularly": "Đi học chuyên cần",\n        "prepared_vietnamese": "Trẻ dân tộc được chuẩn bị tiếng Việt",\n        "weight_monitored": "Được theo dõi bằng biểu đồ cân nặng",\n        "underweight": "Suy dinh dưỡng thể nhẹ cân",\n        "height_monitored": "Được theo dõi bằng biểu đồ chiều cao",\n        "stunted": "Suy dinh dưỡng thể thấp còi",\n        "attends_two_sessions_per_day": "Học 2 buổi/ngày",\n    }\n'''
        new_labels = '''    # Chỉ báo thực sự còn dùng trong theo dõi PCGDMN hiện tại.\n    # Các chỉ báo cũ vẫn nằm trong DB để bảo toàn lịch sử nhưng không đưa vào báo cáo.\n    indicator_labels = {\n        "completed_preschool_by_age": "Hoàn thành Chương trình GDMN theo độ tuổi",\n        "attends_two_sessions_per_day": "Học 2 buổi/ngày",\n        "prepared_vietnamese": "Trẻ dân tộc được chuẩn bị tiếng Việt",\n    }\n'''
        s = replace_once(s, old_labels, new_labels, "danh sach chi bao")
        s = replace_once(s, '            value = row[field_name]\n', '            value = row.get(field_name)\n', "doc chi bao an toan")

        old_totals = '''    completed_preschool_5 = sum(\n        row["completed_preschool_5"] is True for row in person_rows\n    )\n    underweight_people = sum(\n        row["underweight"] is True for row in person_rows\n    )\n    stunted_people = sum(\n        row["stunted"] is True for row in person_rows\n    )\n'''
        new_totals = '''    completed_preschool_by_age = sum(\n        row.get("completed_preschool_by_age") is True for row in person_rows\n    )\n'''
        s = replace_once(s, old_totals, new_totals, "tong chi bao")

        old_return = '''        "completed_preschool_5": completed_preschool_5,\n        "underweight_people": underweight_people,\n        "stunted_people": stunted_people,\n'''
        new_return = '''        "completed_preschool_by_age": completed_preschool_by_age,\n'''
        s = replace_once(s, old_return, new_return, "du lieu tra ve")

        old_overview = '''        (\n            "Đang học",\n            data["studying_people"],\n            "Hoàn thành MN 5 tuổi",\n            data["completed_preschool_5"],\n        ),\n        (\n            "Suy dinh dưỡng nhẹ cân",\n            data["underweight_people"],\n            "Suy dinh dưỡng thấp còi",\n            data["stunted_people"],\n        ),\n'''
        new_overview = '''        (\n            "Đang học",\n            data["studying_people"],\n            "Hoàn thành CTGDMN theo độ tuổi",\n            data["completed_preschool_by_age"],\n        ),\n'''
        s = replace_once(s, old_overview, new_overview, "tong quan Excel")

        old_headers = '''        "Nội dung hỗ trợ",\n        "Hoàn thành MN 5 tuổi",\n        "Đủ ngày",\n        "Chuyên cần",\n        "Chuẩn bị tiếng Việt",\n        "Theo dõi cân nặng",\n        "Nhẹ cân",\n        "Theo dõi chiều cao",\n        "Thấp còi",\n'''
        new_headers = '''        "Nội dung hỗ trợ",\n        "Hoàn thành CTGDMN theo độ tuổi",\n        "Học 2 buổi/ngày",\n        "Chuẩn bị tiếng Việt",\n'''
        s = replace_once(s, old_headers, new_headers, "cot chi tiet Excel")

        old_values = '''            row["disability_support_details"] or "",\n            gia_tri_co_khong(row["completed_preschool_5"]),\n            gia_tri_co_khong(row["attends_required_days"]),\n            gia_tri_co_khong(row["attends_regularly"]),\n            gia_tri_co_khong(row["prepared_vietnamese"]),\n            gia_tri_co_khong(row["weight_monitored"]),\n            gia_tri_co_khong(row["underweight"]),\n            gia_tri_co_khong(row["height_monitored"]),\n            gia_tri_co_khong(row["stunted"]),\n'''
        new_values = '''            row["disability_support_details"] or "",\n            gia_tri_co_khong(row.get("completed_preschool_by_age")),\n            gia_tri_co_khong(row.get("attends_two_sessions_per_day")),\n            gia_tri_co_khong(row.get("prepared_vietnamese")),\n'''
        s = replace_once(s, old_values, new_values, "gia tri chi tiet Excel")

        old_card = '''        <article class="stat-card">\n            <div class="stat-label">Hoàn thành MN 5 tuổi</div>\n            <div class="stat-value">{{ completed_preschool_5 }}</div>\n            <div class="stat-note">Chỉ báo được đánh dấu Có</div>\n        </article>\n'''
        new_card = '''        <article class="stat-card">\n            <div class="stat-label">Hoàn thành CTGDMN theo độ tuổi</div>\n            <div class="stat-value">{{ completed_preschool_by_age }}</div>\n            <div class="stat-note">Chỉ tính chỉ báo đang được theo dõi</div>\n        </article>\n'''
        t = replace_once(t, old_card, new_card, "the tong quan HTML")

        old_panel_desc = '''                    <p class="panel-description">Tổng hợp các chỉ báo Có/Không của năm học hiện tại.</p>'''
        if old_panel_desc in t:
            t = t.replace(old_panel_desc, '''                    <p class="panel-description">Chỉ hiển thị các chỉ báo đang thực sự được theo dõi; chỉ báo cũ đã loại không đưa vào báo cáo.</p>''', 1)
        else:
            # Template cũ có thể không có đúng câu trên; chèn ghi chú ngay trước bảng chỉ báo.
            needle = '''            <div class="table-wrap">\n                <table>\n                    <thead>\n                    <tr><th>STT</th><th>Chỉ báo</th>'''
            if needle in t:
                t = t.replace(needle, '''            <p class="panel-description">Chỉ hiển thị các chỉ báo đang thực sự được theo dõi; chỉ báo cũ đã loại không đưa vào báo cáo.</p>\n            <div class="table-wrap">\n                <table>\n                    <thead>\n                    <tr><th>STT</th><th>Chỉ báo</th>''', 1)

        SURVEYS.write_text(s, encoding="utf-8")
        TEMPLATE.write_text(t, encoding="utf-8")
        print("[CAP NHAT] app\\routers\\surveys.py")
        print("[CAP NHAT] app\\templates\\surveys\\summary_report.html")

        py_compile.compile(str(SURVEYS), doraise=True)
        print("[KIEM TRA] Cu phap Python: OK")

        check = SURVEYS.read_text(encoding="utf-8")
        report_start = check.index("def tao_du_lieu_bao_cao_tong_hop(")
        report_end = check.index("# =========================================================\n# BÀI 12D-7", report_start)
        report_section = check[report_start:report_end]

        required = (
            '"completed_preschool_by_age"',
            '"attends_two_sessions_per_day"',
            '"prepared_vietnamese"',
        )
        for item in required:
            if item not in report_section:
                raise RuntimeError(f"Thieu chi bao dang theo doi: {item}")

        retired_labels = (
            '"attends_required_days": "Đi học đủ ngày theo quy định"',
            '"attends_regularly": "Đi học chuyên cần"',
            '"weight_monitored": "Được theo dõi bằng biểu đồ cân nặng"',
            '"underweight": "Suy dinh dưỡng thể nhẹ cân"',
            '"height_monitored": "Được theo dõi bằng biểu đồ chiều cao"',
            '"stunted": "Suy dinh dưỡng thể thấp còi"',
        )
        if any(item in report_section for item in retired_labels):
            raise RuntimeError("Van con chi bao cu trong Bao cao tong hop.")

        if 'value = row[field_name]' in report_section:
            raise RuntimeError("Bao cao van co nguy co KeyError chi bao.")

        print("[KIEM TRA] Chi bao bao cao: 3 chi bao dang theo doi - OK")
        print("[KIEM TRA] Da loai cac chi bao cu khoi HTML/Excel - OK")
        print("[KIEM TRA] Da chan KeyError chi bao - OK")

    except Exception:
        print("[LOI] Cai dat khong thanh cong. Dang khoi phuc...")
        shutil.copy2(backup_dir / "app" / "routers" / "surveys.py", SURVEYS)
        shutil.copy2(backup_dir / "app" / "templates" / "surveys" / "summary_report.html", TEMPLATE)
        print("[KHOI PHUC] Du an da tro ve trang thai truoc khi cai.")
        raise

    print("\n=== CAI DAT THANH CONG ===")
    print(f"Ban sao an toan: {backup_dir}")
    print("Database phocap.db khong bi thay doi.")
    print("Khoi dong lai Uvicorn va mo lai Bao cao tong hop dot.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[CHI TIET LOI] {type(exc).__name__}: {exc}")
        raise SystemExit(1)
