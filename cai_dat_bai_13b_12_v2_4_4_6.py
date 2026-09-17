from __future__ import annotations

import py_compile
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_PROJECT = Path(r"C:\PhoCap")
TARGET_REL = Path("app/routers/surveys.py")
MARKER = "BAI_13B_12_V2_4_4_6_MOBILE_DYNAMIC_COMPLETION_START"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: can tim dung 1 vi tri, tim thay {count}.")
    return text.replace(old, new, 1)


def patch_source(s: str) -> str:
    if MARKER in s:
        return s

    if "BAI_13B_12_V2_4_3_15_MOBILE_FORM_SCOPE_GUARD_START" not in s:
        raise RuntimeError(
            "Nguon chua co ban khoa quyen dien thoai V2.4.3.15. "
            "Khong tu dong va tren nguon khac de tranh ghi de nham."
        )

    start_token = "def danh_gia_do_day_du_phieu_nhap_nhanh(\n"
    end_token = "\ndef hien_thi_trang_nhap_nhanh(\n"
    start = s.find(start_token)
    if start < 0:
        raise RuntimeError("Khong tim thay ham danh_gia_do_day_du_phieu_nhap_nhanh.")
    end = s.find(end_token, start)
    if end < 0:
        raise RuntimeError("Khong xac dinh duoc diem ket thuc ham danh gia Nhap nhanh.")

    new_func = '''# === BAI_13B_12_V2_4_4_6_MOBILE_DYNAMIC_COMPLETION_START ===
def danh_gia_do_day_du_phieu_nhap_nhanh(
    *,
    db: Session,
    survey_form: SurveyForm,
) -> dict[str, Any]:
    """Đánh giá điều kiện nhập nhanh theo đúng nhóm tuổi/cấp học.

    V2.4.4.6: đồng bộ phần HIỂN THỊ với chính bộ quy tắc động đang
    được dùng khi lưu/hoàn thành phiếu, tránh báo thiếu giả trên điện thoại.
    """

    people = [
        item
        for item in survey_form.household.people
        if item.is_active
    ]
    person_ids = [int(item.id) for item in people]

    records: list[SurveyPersonYearRecord] = []
    if person_ids:
        records = db.scalars(
            select(SurveyPersonYearRecord).where(
                SurveyPersonYearRecord.survey_form_id == survey_form.id,
                SurveyPersonYearRecord.school_year_id
                == survey_form.survey_batch.school_year_id,
                SurveyPersonYearRecord.survey_person_id.in_(person_ids),
            )
        ).all()

    record_map = {
        int(item.survey_person_id): item
        for item in records
    }

    missing_personal_id_count = sum(
        not (item.personal_id or "").strip()
        for item in people
    )
    missing_year_record_count = 0
    incomplete_year_record_count = 0
    school_year = survey_form.survey_batch.school_year

    for person in people:
        record = record_map.get(int(person.id))
        if record is None:
            missing_year_record_count += 1
            continue

        progress = b131133_tien_do_nam_hoc(
            person=person,
            record=record,
            school_year=school_year,
        )
        if not bool(progress["complete"]):
            incomplete_year_record_count += 1

    return {
        "people": people,
        "record_map": record_map,
        "active_people_count": len(people),
        "missing_personal_id_count": int(missing_personal_id_count),
        "missing_year_record_count": int(missing_year_record_count),
        "incomplete_year_record_count": int(incomplete_year_record_count),
    }


# === BAI_13B_12_V2_4_4_6_MOBILE_DYNAMIC_COMPLETION_END ===
'''
    s = s[:start] + new_func + s[end:]

    s = replace_once(
        s,
        '''    user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))
    can_confirm_commune = is_admin_role(role_code)

    head_name = chuan_hoa_van_ban(head_name)
''',
        '''    user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))
    can_confirm_commune = is_admin_role(role_code)

    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_QUICK_START ===
    if not can_edit_survey_data(role_code):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )
    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_QUICK_END ===

    head_name = chuan_hoa_van_ban(head_name)
''',
        "Khoa quyen Luu ho",
    )

    s = replace_once(
        s,
        '''    if survey_form.survey_batch.status == "DA_KET_THUC":
        errors.append("Đợt điều tra đã kết thúc, không thể cập nhật.")
''',
        '''    if (
        survey_form.survey_batch.status == "DA_KET_THUC"
        or survey_form.survey_batch.is_locked
    ):
        errors.append("Đợt điều tra đã khóa/kết thúc, không thể cập nhật.")
''',
        "Khoa dot khi Luu ho",
    )

    s = replace_once(
        s,
        '''    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    full_name = chuan_hoa_van_ban(full_name)
''',
        '''    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_ADD_PERSON_START ===
    role_code = normalize_role_code(
        lay_thong_tin_nguoi_dung(request).get("role_code")
    )
    if not can_edit_survey_data(role_code):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )
    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_ADD_PERSON_END ===

    full_name = chuan_hoa_van_ban(full_name)
''',
        "Khoa quyen Them thanh vien",
    )

    s = replace_once(
        s,
        '''    if survey_form.survey_batch.status == "DA_KET_THUC":
        errors.append("Đợt điều tra đã kết thúc, không thể thêm thành viên.")
''',
        '''    if (
        survey_form.survey_batch.status == "DA_KET_THUC"
        or survey_form.survey_batch.is_locked
    ):
        errors.append("Đợt điều tra đã khóa/kết thúc, không thể thêm thành viên.")
''',
        "Khoa dot khi Them thanh vien",
    )

    fn_pos = s.find("def tong_quan_theo_doi_nam_hoc(")
    if fn_pos < 0:
        raise RuntimeError("Khong tim thay tong_quan_theo_doi_nam_hoc.")
    tail = s[fn_pos:]
    old = '''    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    people = db.scalars(
'''
    new = '''    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    # === BAI_13B_12_V2_4_4_6_YEAR_OVERVIEW_SCOPE_GUARD_START ===
    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )
    # === BAI_13B_12_V2_4_4_6_YEAR_OVERVIEW_SCOPE_GUARD_END ===

    people = db.scalars(
'''
    if tail.count(old) < 1:
        raise RuntimeError("Khong tim thay vi tri khoa Tong quan nam hoc.")
    tail = tail.replace(old, new, 1)
    s = s[:fn_pos] + tail

    s = replace_once(
        s,
        '''    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    school_years = db.scalars(
''',
        '''    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    # === BAI_13B_12_V2_4_4_6_TEACHER_CURRENT_YEAR_GET_START ===
    _mobile_role_code = normalize_role_code(
        lay_thong_tin_nguoi_dung(request).get("role_code")
    )
    if _mobile_role_code == TEACHER_ROLE_CODE:
        school_year_id = int(survey_form.survey_batch.school_year_id)
    # === BAI_13B_12_V2_4_4_6_TEACHER_CURRENT_YEAR_GET_END ===

    school_years = db.scalars(
''',
        "Khoa nam hoc GET",
    )

    s = replace_once(
        s,
        '''    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    errors: list[str] = []

    if survey_form.survey_batch.status == "DA_KET_THUC":
        errors.append(
            "Đợt điều tra đã kết thúc, không thể cập nhật năm học."
        )
''',
        '''    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_YEAR_START ===
    _mobile_role_code = normalize_role_code(
        lay_thong_tin_nguoi_dung(request).get("role_code")
    )
    if not can_edit_survey_data(_mobile_role_code):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )
    if _mobile_role_code == TEACHER_ROLE_CODE:
        school_year_id = int(survey_form.survey_batch.school_year_id)
    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_YEAR_END ===

    errors: list[str] = []

    if (
        survey_form.survey_batch.status == "DA_KET_THUC"
        or survey_form.survey_batch.is_locked
    ):
        errors.append(
            "Đợt điều tra đã khóa/kết thúc, không thể cập nhật năm học."
        )
''',
        "Khoa quyen/nam hoc POST",
    )

    return s


def main() -> int:
    project = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_PROJECT
    target = project / TARGET_REL

    print("BAI 13B-12 V2.4.4.6 - HOAN THIEN DIEN THOAI GIAO VIEN")
    print("- Khong doi giao dien mobile da chot.")
    print("- Dong bo canh bao Nhap nhanh voi quy tac hoan thanh thuc te.")
    print("- Khoa Luu ho/Them thanh vien/Luu nam hoc khi dot bi khoa.")
    print("- Giao vien chi sua dung phieu va nam hoc duoc giao.")
    print("- Khong sua database, bao cao, menu hay template HTML.")
    print()

    if not target.is_file():
        print(f"[LOI] Khong tim thay: {target}")
        return 1

    original = target.read_text(encoding="utf-8")
    if MARKER in original:
        print("[OK] V2.4.4.6 da co trong nguon. Khong va lap lai.")
        try:
            py_compile.compile(str(target), doraise=True)
            print("[KIEM TRA] Cu phap Python: OK")
            return 0
        except Exception as exc:
            print(f"[LOI] Cu phap: {exc}")
            return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = project / "backups" / f"backup_bai_13b_12_v2_4_4_6_{timestamp}"
    backup_file = backup_dir / TARGET_REL

    try:
        patched = patch_source(original)
        backup_file.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(target, backup_file)
        print(f"[BACKUP] {backup_file}")

        target.write_text(patched, encoding="utf-8")
        print(f"[CAP NHAT] {TARGET_REL}")
        py_compile.compile(str(target), doraise=True)
        print("[KIEM TRA] Cu phap Python: OK")

        verify = target.read_text(encoding="utf-8")
        required = [
            MARKER,
            "BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_QUICK_START",
            "BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_ADD_PERSON_START",
            "BAI_13B_12_V2_4_4_6_TEACHER_CURRENT_YEAR_GET_START",
            "BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_YEAR_START",
            "BAI_13B_12_V2_4_4_6_YEAR_OVERVIEW_SCOPE_GUARD_START",
        ]
        missing = [item for item in required if item not in verify]
        if missing:
            raise RuntimeError("Thieu marker sau cai dat: " + ", ".join(missing))
        print("[KIEM TRA] Day du cac khoa bao ve mobile: OK")

    except Exception as exc:
        print(f"[LOI] {type(exc).__name__}: {exc}")
        if backup_file.is_file():
            shutil.copy2(backup_file, target)
            print(f"[KHOI PHUC] {target}")
        print("Du an da duoc dua ve trang thai truoc khi cai dat.")
        return 1

    print()
    print("=== CAI DAT THANH CONG ===")
    print(f"Ban sao an toan: {backup_dir}")
    print("Database phocap.db khong bi thay doi.")
    print("Khoi dong lai Uvicorn va kiem tra tai khoan GIAO_VIEN tren dien thoai.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
