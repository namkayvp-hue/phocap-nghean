from __future__ import annotations

import os
import py_compile
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("PHOCAP_ROOT", r"C:\PhoCap"))
TREND = ROOT / "app" / "routers" / "survey_trends.py"
TEMPLATE = ROOT / "app" / "templates" / "surveys" / "multi_year_trend.html"
MARKER = "BAI_13B_12_V2_4_4_6_6_ACTIVE_TREND_INDICATORS"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: can tim dung 1 vi tri, tim thay {count}. "
            "Dung cai dat de tranh ghi de nham nguon."
        )
    return text.replace(old, new, 1)


def patch_trend_source(text: str) -> str:
    if MARKER in text:
        return text

    text = replace_once(
        text,
        '''from app.routers.surveys import (\n    BOOLEAN_YEAR_FIELDS,\n    FORM_STATUS_LABELS,\n    LEARNING_STATUS_LABELS,\n    lay_thong_tin_nguoi_dung,\n    tao_bo_loc_bao_cao_theo_nguoi_dung,\n    tao_bo_loc_dot_theo_nguoi_dung,\n)\n''',
        '''from app.routers.surveys import (\n    FORM_STATUS_LABELS,\n    LEARNING_STATUS_LABELS,\n    b131133_chuan_hoa_khong_dau,\n    b131133_xac_dinh_cap_hoc,\n    lay_thong_tin_nguoi_dung,\n    tao_bo_loc_bao_cao_theo_nguoi_dung,\n    tao_bo_loc_dot_theo_nguoi_dung,\n)\n''',
        "import quy tac chi bao dong",
    )

    text = replace_once(
        text,
        '''INDICATOR_LABELS = {\n    # === BAI_13B_12_V2_4_4_6_3_TREND_INDICATOR_COMPAT ===\n    "completed_preschool_by_age": "Hoàn thành Chương trình GDMN theo độ tuổi",\n    "completed_preschool_5": "Hoàn thành chương trình mầm non 5 tuổi (dữ liệu cũ)",\n    "attends_required_days": "Đi học đủ ngày theo quy định",\n    "attends_regularly": "Đi học chuyên cần",\n    "prepared_vietnamese": "Trẻ dân tộc được chuẩn bị tiếng Việt",\n    "weight_monitored": "Được theo dõi bằng biểu đồ cân nặng",\n    "underweight": "Suy dinh dưỡng thể nhẹ cân",\n    "height_monitored": "Được theo dõi bằng biểu đồ chiều cao",\n    "stunted": "Suy dinh dưỡng thể thấp còi",\n    "attends_two_sessions_per_day": "Học 2 buổi/ngày",\n}\n\nLEARNING_STATUS_WITH_UNKNOWN = {\n''',
        f'''INDICATOR_LABELS = {{\n    # === BAI_13B_12_V2_4_4_6_3_TREND_INDICATOR_COMPAT ===\n    "completed_preschool_by_age": "Hoàn thành Chương trình GDMN theo độ tuổi",\n    "attends_two_sessions_per_day": "Học 2 buổi/ngày",\n    "prepared_vietnamese": "Trẻ dân tộc được chuẩn bị tiếng Việt",\n}}\n\n# === {MARKER} ===\n# Chi cac chi bao con theo doi moi xuat hien trong xu huong va Excel.\nTRACKED_YEAR_FIELDS = (\n    "completed_preschool_by_age",\n    "attends_two_sessions_per_day",\n    "prepared_vietnamese",\n)\n\nLEARNING_STATUS_WITH_UNKNOWN = {{\n''',
        "danh sach chi bao xu huong",
    )

    text = replace_once(
        text,
        '''def _answered_indicator_total(\n    record: SurveyPersonYearRecord | None,\n) -> int:\n    if record is None:\n        return 0\n\n    return sum(\n        getattr(record, field_name) is not None\n        for field_name in BOOLEAN_YEAR_FIELDS\n    )\n\n\ndef _record_needs_review(\n    record: SurveyPersonYearRecord | None,\n) -> tuple[bool, list[str]]:\n    reasons: list[str] = []\n\n    if record is None:\n        return True, ["Chưa có hồ sơ năm học"]\n\n    learning_status = str(record.learning_status or "CHUA_XAC_DINH")\n    if learning_status == "CHUA_XAC_DINH":\n        reasons.append("Chưa xác định trạng thái học tập")\n\n    if learning_status == "DANG_HOC" and _school_name(record) == "Chưa xác định":\n        reasons.append("Đang học nhưng chưa xác định trường")\n\n    answered = _answered_indicator_total(record)\n    if answered < len(BOOLEAN_YEAR_FIELDS):\n        reasons.append(\n            f"Mới nhập {answered}/{len(BOOLEAN_YEAR_FIELDS)} chỉ báo"\n        )\n\n    return bool(reasons), reasons\n''',
        '''def _tracked_fields_for_record(\n    record: SurveyPersonYearRecord | None,\n    school_year: Any = None,\n) -> tuple[str, ...]:\n    """Chi tra ve cac chi bao thuc su phai theo doi cho doi tuong nay."""\n\n    if record is None:\n        return ()\n\n    person = getattr(record, "survey_person", None)\n    if person is None:\n        return ()\n\n    # Khoi chi bao nay chi ap dung cho doi tuong mam non.\n    if b131133_xac_dinh_cap_hoc(person, record, school_year) != "MN":\n        return ()\n\n    fields = [\n        "completed_preschool_by_age",\n        "attends_two_sessions_per_day",\n    ]\n\n    ethnic_key = b131133_chuan_hoa_khong_dau(\n        getattr(person, "ethnic_group", None)\n    )\n    if ethnic_key and ethnic_key not in {"KINH", "DAN TOC KINH"}:\n        fields.append("prepared_vietnamese")\n\n    return tuple(fields)\n\n\ndef _answered_indicator_total(\n    record: SurveyPersonYearRecord | None,\n    school_year: Any = None,\n) -> int:\n    if record is None:\n        return 0\n\n    return sum(\n        getattr(record, field_name, None) is not None\n        for field_name in _tracked_fields_for_record(record, school_year)\n    )\n\n\ndef _record_needs_review(\n    record: SurveyPersonYearRecord | None,\n    school_year: Any = None,\n) -> tuple[bool, list[str]]:\n    reasons: list[str] = []\n\n    if record is None:\n        return True, ["Chưa có hồ sơ năm học"]\n\n    learning_status = str(record.learning_status or "CHUA_XAC_DINH")\n    if learning_status == "CHUA_XAC_DINH":\n        reasons.append("Chưa xác định trạng thái học tập")\n\n    if learning_status == "DANG_HOC" and _school_name(record) == "Chưa xác định":\n        reasons.append("Đang học nhưng chưa xác định trường")\n\n    required_fields = _tracked_fields_for_record(record, school_year)\n    answered = _answered_indicator_total(record, school_year)\n    if answered < len(required_fields):\n        reasons.append(\n            f"Mới nhập {answered}/{len(required_fields)} chỉ báo cần theo dõi"\n        )\n\n    return bool(reasons), reasons\n''',
        "quy tac day du chi bao",
    )

    text = replace_once(
        text,
        '''    indicator_counts = {\n        field_name: {"yes": 0, "no": 0, "unknown": 0}\n        for field_name in BOOLEAN_YEAR_FIELDS\n    }\n\n    answered_total = 0\n    review_total = 0\n''',
        '''    indicator_counts = {\n        field_name: {"yes": 0, "no": 0, "unknown": 0}\n        for field_name in TRACKED_YEAR_FIELDS\n    }\n\n    answered_total = 0\n    possible_answers = 0\n    review_total = 0\n''',
        "khoi tao dem chi bao",
    )

    text = replace_once(
        text,
        '''        answered_total += _answered_indicator_total(record)\n        needs_review, _ = _record_needs_review(record)\n        review_total += int(needs_review)\n\n        for field_name in BOOLEAN_YEAR_FIELDS:\n            value = getattr(record, field_name)\n            if value is True:\n                indicator_counts[field_name]["yes"] += 1\n            elif value is False:\n                indicator_counts[field_name]["no"] += 1\n            else:\n                indicator_counts[field_name]["unknown"] += 1\n\n    people_total = len(records)\n    possible_answers = people_total * len(BOOLEAN_YEAR_FIELDS)\n''',
        '''        active_fields = _tracked_fields_for_record(record, batch.school_year)\n        answered_total += _answered_indicator_total(record, batch.school_year)\n        possible_answers += len(active_fields)\n        needs_review, _ = _record_needs_review(record, batch.school_year)\n        review_total += int(needs_review)\n\n        for field_name in active_fields:\n            value = getattr(record, field_name, None)\n            if value is True:\n                indicator_counts[field_name]["yes"] += 1\n            elif value is False:\n                indicator_counts[field_name]["no"] += 1\n            else:\n                indicator_counts[field_name]["unknown"] += 1\n\n    people_total = len(records)\n''',
        "dem chi bao theo doi",
    )

    text = replace_once(
        text,
        '''        "preschool_completed": (\n            indicator_counts.get("completed_preschool_by_age", {}).get("yes", 0)\n            or indicator_counts.get("completed_preschool_5", {}).get("yes", 0)\n        ),\n        "underweight_total": indicator_counts["underweight"]["yes"],\n        "stunted_total": indicator_counts["stunted"]["yes"],\n''',
        '''        "preschool_completed": indicator_counts[\n            "completed_preschool_by_age"\n        ]["yes"],\n''',
        "bo tong chi bao cu",
    )

    text = replace_once(
        text,
        '''    indicator_rows = []\n    for field_name in BOOLEAN_YEAR_FIELDS:\n''',
        '''    indicator_rows = []\n    for field_name in TRACKED_YEAR_FIELDS:\n''',
        "bang chi bao xu huong",
    )

    text = text.replace(
        'row["indicator_counts"][field_name]["yes"]',
        'row["indicator_counts"].get(field_name, {}).get("yes", 0)',
    )
    text = text.replace(
        'row["indicator_counts"][field_name]["no"]',
        'row["indicator_counts"].get(field_name, {}).get("no", 0)',
    )
    text = text.replace(
        'row["indicator_counts"][field_name]["unknown"]',
        'row["indicator_counts"].get(field_name, {}).get("unknown", 0)',
    )

    text = text.replace(
        '_record_needs_review(record)',
        '_record_needs_review(record, batch.school_year)',
    )
    text = text.replace(
        '"answered": _answered_indicator_total(record),',
        '"answered": _answered_indicator_total(record, batch.school_year),',
    )
    text = text.replace(
        '"indicator_total": len(BOOLEAN_YEAR_FIELDS),',
        '"indicator_total": len(_tracked_fields_for_record(record, batch.school_year)),',
    )

    text = replace_once(
        text,
        '                "latest_indicator_total": len(BOOLEAN_YEAR_FIELDS),\n',
        '                "latest_indicator_total": (\n                    latest_entry["indicator_total"] if latest_entry else 0\n                ),\n',
        "tong chi bao moi nhat",
    )

    text = replace_once(
        text,
        '''            "Đang học",\n            "Hoàn thành MN 5 tuổi",\n            "Suy dinh dưỡng nhẹ cân",\n            "Suy dinh dưỡng thấp còi",\n            "Tỷ lệ nhập chỉ báo (%)",\n''',
        '''            "Đang học",\n            "Hoàn thành CTGDMN theo độ tuổi",\n            "Tỷ lệ nhập chỉ báo đang theo dõi (%)",\n''',
        "cot Excel theo nam",
    )

    text = replace_once(
        text,
        '''                row["attending_total"],\n                row["preschool_completed"],\n                row["underweight_total"],\n                row["stunted_total"],\n                row["indicator_completion_percent"],\n''',
        '''                row["attending_total"],\n                row["preschool_completed"],\n                row["indicator_completion_percent"],\n''',
        "du lieu Excel theo nam",
    )

    text = replace_once(
        text,
        '        [14, 24, 36, 20, 10, 10, 16, 12, 19, 12, 22, 23, 23, 22, 14, 20],\n',
        '        [14, 24, 36, 20, 10, 10, 16, 12, 19, 12, 30, 30, 14, 20],\n',
        "do rong Excel theo nam",
    )

    text = replace_once(
        text,
        '''        for field_name in BOOLEAN_YEAR_FIELDS:\n            counts = row["indicator_counts"][field_name]\n''',
        '''        for field_name in TRACKED_YEAR_FIELDS:\n            counts = row["indicator_counts"].get(\n                field_name, {"yes": 0, "no": 0, "unknown": 0}\n            )\n''',
        "sheet chi bao theo nam",
    )

    return text


def patch_template(text: str) -> str:
    if "BAI_13B_12_V2_4_4_6_6_TREND_UI" in text:
        return text

    text = replace_once(
        text,
        '''                        <th>Hoàn thành MN 5 tuổi</th>\n                        <th>Nhẹ cân</th>\n                        <th>Thấp còi</th>\n                        <th>Nhập chỉ báo</th>\n''',
        '''                        <th>Hoàn thành CTGDMN theo độ tuổi</th>\n                        <th>Nhập chỉ báo cần theo dõi</th>\n''',
        "tieu de bang xu huong",
    )

    text = replace_once(
        text,
        '''                            <td>{{ row.preschool_completed }}</td>\n                            <td>{{ row.underweight_total }}</td>\n                            <td>{{ row.stunted_total }}</td>\n                            <td><strong>{{ row.indicator_completion_percent }}%</strong></td>\n''',
        '''                            <td>{{ row.preschool_completed }}</td>\n                            <td><strong>{{ row.indicator_completion_percent }}%</strong></td>\n''',
        "du lieu bang xu huong",
    )

    text = replace_once(
        text,
        '''                    <h2>Kết quả Có / Không / Chưa xác định</h2>\n                </div>\n''',
        '''                    <h2>Kết quả Có / Không / Chưa xác định</h2>\n                    <!-- === BAI_13B_12_V2_4_4_6_6_TREND_UI === -->\n                    <p class="panel-description">Chỉ hiển thị chỉ báo còn theo dõi; chỉ báo không áp dụng cho đối tượng không tính vào “Chưa xác định”.</p>\n                </div>\n''',
        "ghi chu chi bao",
    )
    return text


def main() -> int:
    print("BAI 13B-12 V2.4.4.6.6 - DONG BO CHI BAO THEO DOI")
    print("- Dong bo Bao cao tong hop va 2.4.3 xu huong lien nam.")
    print("- An chi bao cu khoi giao dien va Excel xu huong.")
    print("- Chi bao khong ap dung cho doi tuong khong bi tinh la Chua ro.")
    print("- Khong xoa du lieu cu va khong sua database.\n")

    if not TREND.exists() or not TEMPLATE.exists():
        raise FileNotFoundError("Khong tim thay survey_trends.py hoac multi_year_trend.html")

    original_trend = TREND.read_text(encoding="utf-8")
    original_template = TEMPLATE.read_text(encoding="utf-8")

    if MARKER in original_trend and "BAI_13B_12_V2_4_4_6_6_TREND_UI" in original_template:
        print("[THONG TIN] V2.4.4.6.6 da duoc cai. Khong sua lap.")
        return 0

    # Ban nay duoc cai sau 6.3 va 6.2. Neu nguon khong dung, dung lai de bao ve du an.
    if "BAI_13B_12_V2_4_4_6_3_TREND_INDICATOR_COMPAT" not in original_trend:
        raise RuntimeError("Chua thay dau V2.4.4.6.3 trong survey_trends.py.")
    if "BAI_13B_12_V2_4_4_6_2_ROADMAP_SIM_START" not in original_template:
        raise RuntimeError("Chua thay Dashboard 2.4.3 V2.4.4.6.2 trong template.")

    patched_trend = patch_trend_source(original_trend)
    patched_template = patch_template(original_template)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / "backups" / f"backup_bai_13b_12_v2_4_4_6_6_{stamp}"
    backup_trend = backup_dir / "app" / "routers" / "survey_trends.py"
    backup_template = backup_dir / "app" / "templates" / "surveys" / "multi_year_trend.html"
    backup_trend.parent.mkdir(parents=True, exist_ok=True)
    backup_template.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TREND, backup_trend)
    shutil.copy2(TEMPLATE, backup_template)
    print(f"[BACKUP] {backup_dir}")

    try:
        TREND.write_text(patched_trend, encoding="utf-8")
        TEMPLATE.write_text(patched_template, encoding="utf-8")
        print("[CAP NHAT] app\\routers\\survey_trends.py")
        print("[CAP NHAT] app\\templates\\surveys\\multi_year_trend.html")

        py_compile.compile(str(TREND), doraise=True)
        print("[KIEM TRA] Cu phap Python: OK")

        from jinja2 import Environment
        Environment().parse(TEMPLATE.read_text(encoding="utf-8"))
        print("[KIEM TRA] Cu phap Jinja: OK")

        check = TREND.read_text(encoding="utf-8")
        template_check = TEMPLATE.read_text(encoding="utf-8")

        required = [
            MARKER,
            'TRACKED_YEAR_FIELDS = (',
            '"completed_preschool_by_age"',
            '"attends_two_sessions_per_day"',
            '"prepared_vietnamese"',
            '_tracked_fields_for_record(',
        ]
        missing = [item for item in required if item not in check]
        if missing:
            raise RuntimeError("Thieu khoa sau cai dat: " + repr(missing))

        retired_ui = [
            "<th>Nhẹ cân</th>",
            "<th>Thấp còi</th>",
        ]
        if any(item in template_check for item in retired_ui):
            raise RuntimeError("Van con cot chi bao cu trong giao dien xu huong.")

        # Trong phan thong ke xu huong khong duoc dung BOOLEAN_YEAR_FIELDS nua.
        trend_core_start = check.index("def _answered_indicator_total(")
        trend_core_end = check.index("# =========================================================\n# API DASHBOARD", trend_core_start) if "# =========================================================\n# API DASHBOARD" in check[trend_core_start:] else len(check)
        trend_core = check[trend_core_start:trend_core_end]
        if "BOOLEAN_YEAR_FIELDS" in trend_core:
            raise RuntimeError("Van con dem chi bao cu trong loi xu huong.")

        print("[KIEM TRA] Chi con 3 chi bao dang theo doi: OK")
        print("[KIEM TRA] Chi bao khong ap dung khong tinh Chua ro: OK")
        print("[KIEM TRA] Excel xu huong da loai chi bao cu: OK")

    except Exception:
        shutil.copy2(backup_trend, TREND)
        shutil.copy2(backup_template, TEMPLATE)
        print("[KHOI PHUC] Da dua 2 tep ve trang thai truoc khi cai.")
        raise

    print("\n=== CAI DAT THANH CONG ===")
    print(f"Ban sao an toan: {backup_dir}")
    print("Database phocap.db khong bi thay doi.")
    print("Khoi dong lai Uvicorn va kiem tra Bao cao tong hop + 2.4.3.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[LOI] {type(exc).__name__}: {exc}")
        raise SystemExit(1)
