from __future__ import annotations

from pathlib import Path
from datetime import datetime
import shutil

VERSION = "BAI 13B-12 V2.4.4.5"
MARKER = "BAI_13B_12_V2_4_4_5_TH02_DIAGNOSTIC_SOURCE"
REQUIRED_PREVIOUS = "BAI_13B_12_V2_4_4_4_TH02_REUSE_PRIOR_DATA"
PATCH_BLOCK = '# === BAI_13B_12_V2_4_4_5_TH02_DIAGNOSTIC_SOURCE_START ===\n# Sửa theo kết quả chẩn đoán thực tế Xã Nghi Lộc:\n# - 5/5 trường TH có dữ liệu mạng lưới năm gần nhất và national_standard=1.\n# - 5/5 có TH_01_GV (ít nhất năm gần nhất), nhưng 4/5 chưa từng có TH_01_CSVC.\n# - Vì vậy không buộc nhập lại checklist mới chỉ để kết luận TH-02.\n#\n# Nguyên tắc fallback:\n# 1) Cờ PCGD tường minh trong TH_01_GV/TH_01_CSVC luôn ưu tiên cao nhất.\n#    Có cờ Không => Không đảm bảo, không bị fallback ghi đè.\n# 2) Nếu chỉ thiếu các cờ định tính mới, trường đã có national_standard=1 trong\n#    dữ liệu mạng lưới được dùng như minh chứng dự phòng cho điều kiện đội ngũ/\n#    CSVC. Tỷ lệ phòng/lớp và dữ liệu giáo viên/lớp vẫn kiểm tra riêng.\n# 3) Nếu không có national_standard=1 và cũng thiếu cờ chi tiết thì vẫn giữ\n#    Chưa đủ dữ liệu; không suy diễn.\n# 4) Chỉ đọc database, không INSERT/UPDATE/DELETE.\n\n_b2445_previous_staff_status_for_school = _b2443_staff_status_for_school\n_b2445_previous_csvc_status_for_school = _b2443_csvc_status_for_school\n\n\ndef _b2445_boolish(value: Any) -> bool | None:\n    if value is None or value == "":\n        return None\n    if value is True:\n        return True\n    if value is False:\n        return False\n    try:\n        number = float(value)\n    except (TypeError, ValueError):\n        number = None\n    if number is not None:\n        if abs(number - 1.0) < 1e-9:\n            return True\n        if abs(number) < 1e-9:\n            return False\n    text = _norm(value)\n    if text in {"CO", "YES", "TRUE", "DAT", "DAT CHUAN", "DAM BAO"}:\n        return True\n    if text in {"KHONG", "NO", "FALSE", "KHONG DAT", "CHUA DAT", "KHONG DAM BAO"}:\n        return False\n    return None\n\n\ndef _b2445_network_national_standard(\n    db: Session,\n    *,\n    school_id: int,\n    school_year_id: int,\n) -> bool | None:\n    network = _network_reference_data(\n        db,\n        school_id=int(school_id),\n        level="TH",\n        target_year_id=int(school_year_id),\n    )\n    return _b2445_boolish(network.get("national_standard"))\n\n\ndef _b2445_teacher_total(\n    db: Session,\n    *,\n    school_id: int,\n    school_year_id: int,\n    saved_staff: dict[str, Any],\n) -> float | None:\n    value = _b2443_number(saved_staff, "teacher_total")\n    if value is not None and value > 0:\n        return value\n    network = _network_reference_data(\n        db,\n        school_id=int(school_id),\n        level="TH",\n        target_year_id=int(school_year_id),\n    )\n    try:\n        value = float(network.get("teachers"))\n    except (TypeError, ValueError):\n        return None\n    return value if value > 0 else None\n\n\ndef _b2443_staff_status_for_school(\n    db: Session,\n    *,\n    school_id: int,\n    school_year_id: int,\n    grades: dict[int, list[int]],\n    saved_staff: dict[str, Any],\n    saved_csvc: dict[str, Any],\n) -> tuple[str, list[str]]:\n    # Trước hết dùng toàn bộ logic V2.4.4.4.\n    status, missing = _b2445_previous_staff_status_for_school(\n        db,\n        school_id=int(school_id),\n        school_year_id=int(school_year_id),\n        grades=grades,\n        saved_staff=saved_staff,\n        saved_csvc=saved_csvc,\n    )\n    if status != "Chưa xác nhận":\n        return status, missing\n\n    # Một cờ tường minh "Không" luôn thắng fallback.\n    explicit_flags = [\n        _b2443_flag(saved_staff, key)\n        for key in _B2441_STAFF_VERIFY_KEYS\n    ]\n    if any(flag is False for flag in explicit_flags):\n        return "Chưa đạt", [f"school_id={school_id}: có điều kiện đội ngũ được xác nhận Không"]\n\n    # Chỉ fallback khi dữ liệu mạng lưới chính thức của trường ghi nhận\n    # national_standard=1.\n    if _b2445_network_national_standard(\n        db,\n        school_id=int(school_id),\n        school_year_id=int(school_year_id),\n    ) is not True:\n        return status, missing\n\n    # Vẫn kiểm tra tối thiểu giáo viên/lớp, không dùng national_standard để che\n    # một thiếu hụt số lượng rõ ràng.\n    class_total = _class_count_with_network(\n        db,\n        school_id=int(school_id),\n        school_year_id=int(school_year_id),\n        grades=grades,\n        level="TH",\n    )\n    teacher_total = _b2445_teacher_total(\n        db,\n        school_id=int(school_id),\n        school_year_id=int(school_year_id),\n        saved_staff=saved_staff,\n    )\n    if class_total <= 0 or teacher_total is None:\n        return status, missing\n    if teacher_total + 1e-9 < float(class_total):\n        return "Chưa đạt", [f"school_id={school_id}: số giáo viên thấp hơn số lớp"]\n\n    # Người theo dõi PCGD: cờ tường minh nếu có; nếu chưa có thì dùng chính\n    # việc trường đã vận hành dữ liệu PCGD/tài khoản trường làm minh chứng.\n    tracker = _b2443_flag(saved_staff, "pcgd_tracker_assigned")\n    if tracker is False:\n        return "Chưa đạt", [f"school_id={school_id}: chưa phân công người theo dõi PCGD-XMC"]\n    if tracker is None:\n        tracker = bool(\n            saved_staff\n            or saved_csvc\n            or _b2443_school_has_pcgd_responsible_account(db, int(school_id))\n        )\n    if not tracker:\n        return status, missing\n\n    return "Đạt", []\n\n\ndef _b2445_room_ratio(\n    db: Session,\n    *,\n    school_id: int,\n    school_year_id: int,\n    grades: dict[int, list[int]],\n    saved: dict[str, Any],\n) -> bool | None:\n    values = _b2444_currentize_csvc_values(\n        db,\n        school_id=int(school_id),\n        school_year_id=int(school_year_id),\n        grades=grades,\n        saved=saved,\n    )\n    classes = _b2443_number(values, "class_total")\n    rooms = [\n        _b2443_number(values, key)\n        for key in (\n            "room_permanent",\n            "room_semi_permanent",\n            "room_temporary",\n            "room_rent_borrow",\n        )\n    ]\n    if classes is None or classes <= 0 or all(value is None for value in rooms):\n        return None\n    return (sum(value or 0.0 for value in rooms) / classes) + 1e-9 >= 0.7\n\n\ndef _b2443_csvc_status_for_school(\n    db: Session,\n    *,\n    school_id: int,\n    school_year_id: int,\n    grades: dict[int, list[int]],\n    saved: dict[str, Any],\n) -> tuple[str, list[str]]:\n    # Trước hết dùng toàn bộ logic V2.4.4.3/V2.4.4.4.\n    status, missing = _b2445_previous_csvc_status_for_school(\n        db,\n        school_id=int(school_id),\n        school_year_id=int(school_year_id),\n        grades=grades,\n        saved=saved,\n    )\n    if status != "Chưa xác nhận":\n        return status, missing\n\n    # Cờ tường minh "Không" luôn thắng.\n    explicit_flags = [\n        _b2443_flag(saved, key)\n        for key in _B2441_FACILITY_VERIFY_KEYS\n    ]\n    if any(flag is False for flag in explicit_flags):\n        return "Chưa đạt", [f"school_id={school_id}: có điều kiện CSVC/TBDH được xác nhận Không"]\n\n    if _b2445_network_national_standard(\n        db,\n        school_id=int(school_id),\n        school_year_id=int(school_year_id),\n    ) is not True:\n        return status, missing\n\n    # Tỷ lệ phòng/lớp là chỉ tiêu định lượng bắt buộc, vẫn kiểm tra riêng.\n    room_ok = _b2445_room_ratio(\n        db,\n        school_id=int(school_id),\n        school_year_id=int(school_year_id),\n        grades=grades,\n        saved=saved,\n    )\n    if room_ok is False:\n        return "Chưa đạt", [f"school_id={school_id}: tỷ lệ phòng/lớp dưới 0,7"]\n    if room_ok is None:\n        return status, missing\n\n    return "Đạt", []\n\n\n# BAI_13B_12_V2_4_4_5_TH02_DIAGNOSTIC_SOURCE\n# === BAI_13B_12_V2_4_4_5_TH02_DIAGNOSTIC_SOURCE_END ===\n'


def find_project_root() -> Path:
    candidates = [Path(r"C:\PhoCap"), Path.cwd()]
    for root in candidates:
        if (root / "app" / "pcgd_xmc_report_builders_v1.py").exists():
            return root
    raise FileNotFoundError(r"Khong tim thay du an C:\PhoCap.")


def main() -> int:
    print(VERSION)
    print("- TH-02 cap Xa: sua theo ket qua chan doan truc tiep database Nghi Loc.")
    print("- Khong bat 4 truong TH nhap lai TH-01-CSVC chi de xac nhan cot 19.")
    print("- Uu tien co xac nhan PCGD tuong minh; national_standard=1 chi la fallback khi thieu co dinh tinh.")
    print("- Van kiem tra rieng ty le phong/lop >= 0,7 va du lieu GV/lop.")
    print("- Khong sua database, mau Excel, menu, giao dien hay dien thoai.\n")

    root = find_project_root()
    target = root / "app" / "pcgd_xmc_report_builders_v1.py"
    original = target.read_text(encoding="utf-8")

    if MARKER in original:
        print("[OK] V2.4.4.5 da co trong ma nguon. Khong can cai lai.")
        return 0
    if REQUIRED_PREVIOUS not in original:
        print("[LOI] Chua tim thay V2.4.4.4. Hay cai V2.4.4.4 truoc.")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "backups" / f"backup_bai_13b_12_v2_4_4_5_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_file = backup_dir / target.name
    shutil.copy2(target, backup_file)
    print(f"[BACKUP] {backup_file}")

    try:
        new_text = original.rstrip() + "\n\n" + PATCH_BLOCK.lstrip()
        compile(new_text, str(target), "exec")
        target.write_text(new_text, encoding="utf-8")
        compile(target.read_text(encoding="utf-8"), str(target), "exec")
        print(r"[OK] Da cap nhat app\pcgd_xmc_report_builders_v1.py")
        print("[OK] Kiem tra cu phap Python: DAT")
        print("\n=== CAI DAT THANH CONG ===")
        print(f"Ban sao an toan: {backup_dir}")
        print("Database phocap.db khong bi thay doi.")
        print("Khoi dong lai Uvicorn va xuat lai TH-02 cap Xa Nghi Loc.")
        return 0
    except Exception as exc:
        print(f"[LOI] {type(exc).__name__}: {exc}")
        print("Dang khoi phuc tep da sao luu...")
        try:
            shutil.copy2(backup_file, target)
            print(f"[KHOI PHUC] {target}")
            print("Du an da duoc dua ve trang thai truoc khi cai dat.")
        except Exception as restore_exc:
            print(f"[CANH BAO] Khong khoi phuc tu dong duoc: {restore_exc}")
            print(f"Ban backup van nam tai: {backup_file}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
