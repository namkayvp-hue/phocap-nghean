from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
TARGET = PROJECT / "app" / "routers" / "survey_trends.py"
MARKER = "BAI_13B_12_V2_4_4_6_3_TREND_INDICATOR_COMPAT"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: can tim dung 1 vi tri, tim thay {count}.")
    return text.replace(old, new, 1)


def patch_source(text: str) -> str:
    if MARKER in text:
        return text

    # Đồng bộ nhãn với BOOLEAN_YEAR_FIELDS hiện hành trong surveys.py.
    text = replace_once(
        text,
        'INDICATOR_LABELS = {\n    "completed_preschool_5": "Hoàn thành chương trình mầm non 5 tuổi",',
        'INDICATOR_LABELS = {\n    # === BAI_13B_12_V2_4_4_6_3_TREND_INDICATOR_COMPAT ===\n'
        '    "completed_preschool_by_age": "Hoàn thành Chương trình GDMN theo độ tuổi",\n'
        '    "completed_preschool_5": "Hoàn thành chương trình mầm non 5 tuổi (dữ liệu cũ)",',
        "Dong bo nhan chi bao MN",
    )

    # Không truy cập cứng khóa cũ đã không còn nằm trong BOOLEAN_YEAR_FIELDS.
    text = replace_once(
        text,
        '        "preschool_completed": indicator_counts["completed_preschool_5"]["yes"],',
        '        "preschool_completed": (\n'
        '            indicator_counts.get("completed_preschool_by_age", {}).get("yes", 0)\n'
        '            or indicator_counts.get("completed_preschool_5", {}).get("yes", 0)\n'
        '        ),',
        "Sua KeyError completed_preschool_5",
    )

    # Các vòng lặp theo BOOLEAN_YEAR_FIELDS phải luôn có nhãn an toàn.
    text = text.replace(
        '"label": INDICATOR_LABELS[field_name],',
        '"label": INDICATOR_LABELS.get(field_name, field_name),',
    )
    text = text.replace(
        'INDICATOR_LABELS[field_name],',
        'INDICATOR_LABELS.get(field_name, field_name),',
    )

    return text


def main() -> None:
    print("BAI 13B-12 V2.4.4.6.3 - SUA LOI 2.4.3 KEYERROR")
    print("- Sua KeyError: completed_preschool_5 trong survey_trends.py.")
    print("- Dong bo ten chi bao moi completed_preschool_by_age.")
    print("- Giu nguyen Dashboard mo phong 2026-2030 va man hinh Chot so lieu.")
    print("- Khong sua database, menu, bao cao hay dien thoai.\n")

    if not TARGET.exists():
        raise FileNotFoundError(f"Khong tim thay: {TARGET}")

    original = TARGET.read_text(encoding="utf-8")
    patched = patch_source(original)

    if patched == original and MARKER in original:
        print("[THONG TIN] V2.4.4.6.3 da duoc cai truoc do. Khong can sua lai.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = PROJECT / "backups" / f"backup_bai_13b_12_v2_4_4_6_3_{stamp}"
    backup_file = backup_dir / "app" / "routers" / "survey_trends.py"
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, backup_file)
    print(f"[BACKUP] {backup_file}")

    try:
        TARGET.write_text(patched, encoding="utf-8")
        print("[CAP NHAT] app\\routers\\survey_trends.py")

        py_compile.compile(str(TARGET), doraise=True)
        print("[KIEM TRA] Cu phap Python: OK")

        check = TARGET.read_text(encoding="utf-8")
        required = [
            MARKER,
            '"completed_preschool_by_age": "Hoàn thành Chương trình GDMN theo độ tuổi"',
            'indicator_counts.get("completed_preschool_by_age", {}).get("yes", 0)',
            'INDICATOR_LABELS.get(field_name, field_name)',
        ]
        missing = [item for item in required if item not in check]
        if missing:
            raise RuntimeError("Thieu khoa kiem tra sau khi cai: " + repr(missing))

        # Lỗi đúng như traceback của người dùng phải không còn tồn tại.
        if 'indicator_counts["completed_preschool_5"]["yes"]' in check:
            raise RuntimeError("Van con truy cap cung completed_preschool_5 trong _build_year_row.")
        print("[KIEM TRA] Tuong thich chi bao lien nam: OK")

    except Exception:
        shutil.copy2(backup_file, TARGET)
        print("[KHOI PHUC] Da dua survey_trends.py ve ban truoc khi cai.")
        raise

    print("\n=== CAI DAT THANH CONG ===")
    print(f"Ban sao an toan: {backup_dir}")
    print("Database phocap.db khong bi thay doi.")
    print("Khoi dong lai Uvicorn va mo lai muc 2.4.3.")


if __name__ == "__main__":
    main()
