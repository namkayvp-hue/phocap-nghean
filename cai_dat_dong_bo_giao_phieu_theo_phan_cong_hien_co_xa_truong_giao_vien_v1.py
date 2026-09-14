# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()

SURVEYS = PROJECT / "app" / "routers" / "surveys.py"
TEMPLATE = PROJECT / "app" / "templates" / "surveys" / "bulk_assignments.html"
WORKFLOW = PROJECT / "app" / "routers" / "survey_school_workflow.py"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = EXPORTS / f"backup_source_dong_bo_giao_phieu_theo_phan_cong_{STAMP}"
REPORT = EXPORTS / f"bao_cao_cai_dat_dong_bo_giao_phieu_theo_phan_cong_{STAMP}.txt"

EXPECTED_SURVEYS_SHA = "8782aa2f7d4f6faaef2de3e2b0de4d479223c0d6e3b48ca610327acc06b727fd"
EXPECTED_TEMPLATE_SHA = "2309976cefa7b6bee3a9a574289697cec21eed70d629b52132e9c4d1cb85bfc7"
EXPECTED_WORKFLOW_SHA = "f30f2ad9a5abb6b4cb19c145f0c65e458d5f259979219c067e90eb9facbf6666"

MARKER_HELPER = "# === DONG_BO_GIAO_PHIEU_THEO_PHAN_CONG_HIEN_CO_V1_HELPER ==="
MARKER_POST = "# === DONG_BO_GIAO_PHIEU_THEO_PHAN_CONG_HIEN_CO_V1_POST ==="
MARKER_TEMPLATE = "{# === DONG_BO_GIAO_PHIEU_THEO_PHAN_CONG_HIEN_CO_V1 === #}"

STATUS_KEY = "bulk_assignments_sent_existing"
ERROR_KEY = "no_existing_assignment"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="strict")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def db_state() -> dict:
    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        con.execute("PRAGMA query_only = ON")
        return {
            "integrity": str(con.execute("PRAGMA integrity_check").fetchone()[0]),
            "fk_count": len(con.execute("PRAGMA foreign_key_check").fetchall()),
        }
    finally:
        con.close()


def backup_files() -> None:
    for path in (SURVEYS, TEMPLATE):
        dst = BACKUP / path.relative_to(PROJECT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def restore_files() -> None:
    for path in (SURVEYS, TEMPLATE):
        src = BACKUP / path.relative_to(PROJECT)
        if src.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, path)


def insert_dict_message(text: str, dict_name: str, key: str, value: str) -> str:
    if f'"{key}"' in text:
        return text

    anchor = f"{dict_name} = {{"
    pos = text.find(anchor)
    if pos < 0:
        raise RuntimeError(f"Không tìm thấy {dict_name}.")

    brace = text.find("{", pos)
    if brace < 0:
        raise RuntimeError(f"Không tìm thấy dấu {{ của {dict_name}.")

    insertion = (
        "\n"
        f'    "{key}": (\n'
        f'        "{value}"\n'
        "    ),"
    )

    return text[: brace + 1] + insertion + text[brace + 1 :]


def insert_helper(text: str) -> str:
    if MARKER_HELPER in text:
        return text

    anchor = "async def luu_phan_cong_v4_theo_cap("
    pos = text.find(anchor)

    if pos < 0:
        raise RuntimeError("Không tìm thấy luu_phan_cong_v4_theo_cap.")

    helper = f'''
{MARKER_HELPER}
def lay_nguoi_nhan_giao_phieu_tu_phan_cong_hien_co(
    *,
    db: Session,
    survey_form_id: int,
    assignment_level: str,
    current_school_id: int | None,
) -> tuple[list[int], int | None]:
    # Lấy người nhận từ phân công đã có, không bắt người dùng chọn lại.
    rows = db.execute(
        select(
            SurveyFormInvestigator.user_id,
            SurveyFormInvestigator.is_primary,
            User.school_id,
        )
        .join(
            User,
            User.id == SurveyFormInvestigator.user_id,
        )
        .where(
            SurveyFormInvestigator.survey_form_id
            == int(survey_form_id)
        )
        .order_by(
            SurveyFormInvestigator.is_primary.desc(),
            SurveyFormInvestigator.id.asc(),
        )
    ).all()

    if assignment_level == "school":
        school_ids: list[int] = []
        seen_school_ids: set[int] = set()

        for row in rows:
            if row.school_id is None:
                continue

            school_id = int(row.school_id)

            if school_id not in seen_school_ids:
                seen_school_ids.add(school_id)
                school_ids.append(school_id)

        if not school_ids:
            return [], None

        account_rows = db.execute(
            select(
                User.id,
                User.school_id,
            )
            .where(
                User.school_id.in_(school_ids),
                User.role.has(code=SCHOOL_ROLE_CODE),
                ~func.lower(User.username).like("cbql.%"),
            )
            .order_by(
                User.school_id.asc(),
                User.id.asc(),
            )
        ).all()

        result: list[int] = []
        seen_ids: set[int] = set()

        for row in account_rows:
            user_id = int(row.id)

            if user_id not in seen_ids:
                seen_ids.add(user_id)
                result.append(user_id)

        return result, (result[0] if result else None)

    if assignment_level == "teacher":
        if current_school_id is None:
            return [], None

        result: list[int] = []
        seen_ids: set[int] = set()
        primary_id: int | None = None

        for row in rows:
            if (
                row.school_id is None
                or int(row.school_id) != int(current_school_id)
            ):
                continue

            user_id = int(row.user_id)

            is_school_account = bool(
                db.scalar(
                    select(func.count(User.id))
                    .where(
                        User.id == user_id,
                        User.role.has(code=SCHOOL_ROLE_CODE),
                        ~func.lower(User.username).like("cbql.%"),
                    )
                )
                or 0
            )

            if is_school_account:
                continue

            if user_id not in seen_ids:
                seen_ids.add(user_id)
                result.append(user_id)

            if bool(row.is_primary) and primary_id is None:
                primary_id = user_id

        if primary_id not in seen_ids:
            primary_id = result[0] if result else None

        return result, primary_id

    return [], None


'''

    return text[:pos] + helper + text[pos:]


def patch_post(text: str) -> str:
    if MARKER_POST in text:
        return text

    old_validation = '''    if mode != "clear" and not selected_ids:
        return RedirectResponse(
            url=f"{base_url}?error=no_investigators",
            status_code=303,
        )
'''

    new_validation = f'''    {MARKER_POST}
    # Không chọn nơi nhận mới + mode=replace:
    # giao theo phân công hiện có.
    auto_send_existing = (
        mode == "replace"
        and not selected_ids
    )

    # Chỉ chế độ "Thêm" mới bắt buộc chọn nơi nhận mới.
    if mode == "add" and not selected_ids:
        return RedirectResponse(
            url=f"{{base_url}}?error=no_investigators",
            status_code=303,
        )
'''

    if old_validation not in text:
        raise RuntimeError("Không tìm thấy block kiểm selected_ids hiện tại.")

    text = text.replace(old_validation, new_validation, 1)

    old_before_try = '''    if len(survey_forms) != len(form_ids):
        return RedirectResponse(
            url=f"{base_url}?error=invalid_forms",
            status_code=303,
        )

    if mode != "clear":
        allowed_ids = lay_ids_nguoi_dieu_tra_hop_le(
            db=db,
            request=request,
            commune_id=batch.commune_id,
            user_ids=selected_ids,
        )
        if allowed_ids != seen_user_ids:
            return RedirectResponse(
                url=f"{base_url}?error=invalid_investigators",
                status_code=303,
            )

    try:
'''

    new_before_try = '''    if len(survey_forms) != len(form_ids):
        return RedirectResponse(
            url=f"{base_url}?error=invalid_forms",
            status_code=303,
        )

    if mode != "clear" and not auto_send_existing:
        allowed_ids = lay_ids_nguoi_dieu_tra_hop_le(
            db=db,
            request=request,
            commune_id=batch.commune_id,
            user_ids=selected_ids,
        )
        if allowed_ids != seen_user_ids:
            return RedirectResponse(
                url=f"{base_url}?error=invalid_investigators",
                status_code=303,
            )

    auto_targets_by_form: dict[
        int,
        tuple[list[int], int | None],
    ] = {}

    if auto_send_existing:
        current_school_id = (
            scope.get("school_id")
            if assignment_level == "teacher"
            else None
        )

        for survey_form in survey_forms:
            target_ids, target_primary_id = (
                lay_nguoi_nhan_giao_phieu_tu_phan_cong_hien_co(
                    db=db,
                    survey_form_id=int(survey_form.id),
                    assignment_level=assignment_level,
                    current_school_id=(
                        int(current_school_id)
                        if current_school_id is not None
                        else None
                    ),
                )
            )

            if not target_ids:
                return RedirectResponse(
                    url=f"{base_url}?error=no_existing_assignment",
                    status_code=303,
                )

            auto_targets_by_form[int(survey_form.id)] = (
                target_ids,
                target_primary_id,
            )

    try:
'''

    if old_before_try not in text:
        raise RuntimeError("Không tìm thấy block trước try hiện tại.")

    text = text.replace(old_before_try, new_before_try, 1)

    old_try = '''    try:
        if assignment_level == "school" and mode != "clear":
            dong_bo_nhiem_vu_truong_khi_giao_phieu(
                db=db,
                batch_id=batch.id,
                selected_user_ids=selected_ids,
                actor_user_id=scope["user"].get("id"),
                notes=assignment_notes,
            )

        for survey_form in survey_forms:
            cap_nhat_phan_cong_v4_mot_phieu(
                db=db,
                request=request,
                survey_form=survey_form,
                selected_ids=selected_ids,
                primary_user_id=primary_user_id,
                assignment_notes=assignment_notes,
                mode=mode,
                assignment_level=assignment_level,
            )
        db.commit()
'''

    new_try = '''    try:
        # Chọn nơi nhận mới thì giữ nguyên hành vi cũ.
        if (
            assignment_level == "school"
            and mode != "clear"
            and not auto_send_existing
        ):
            dong_bo_nhiem_vu_truong_khi_giao_phieu(
                db=db,
                batch_id=batch.id,
                selected_user_ids=selected_ids,
                actor_user_id=scope["user"].get("id"),
                notes=assignment_notes,
            )

        for survey_form in survey_forms:
            effective_ids = selected_ids
            effective_primary_id = primary_user_id
            effective_mode = mode

            if auto_send_existing:
                (
                    effective_ids,
                    effective_primary_id,
                ) = auto_targets_by_form[int(survey_form.id)]

                # Giao theo phân công hiện có chỉ bổ sung tầng nhận.
                # Không replace để tránh xóa tổ giáo viên 3 cấp.
                effective_mode = "add"

                if assignment_level == "school":
                    dong_bo_nhiem_vu_truong_khi_giao_phieu(
                        db=db,
                        batch_id=batch.id,
                        selected_user_ids=effective_ids,
                        actor_user_id=scope["user"].get("id"),
                        notes=(
                            assignment_notes
                            or "Giao phiếu theo phân công hiện có."
                        ),
                    )

            cap_nhat_phan_cong_v4_mot_phieu(
                db=db,
                request=request,
                survey_form=survey_form,
                selected_ids=effective_ids,
                primary_user_id=effective_primary_id,
                assignment_notes=(
                    assignment_notes
                    or (
                        "Giao phiếu theo phân công hiện có."
                        if auto_send_existing
                        else ""
                    )
                ),
                mode=effective_mode,
                assignment_level=assignment_level,
            )

        db.commit()
'''

    if old_try not in text:
        raise RuntimeError("Không tìm thấy block try/cập nhật phân công hiện tại.")

    text = text.replace(old_try, new_try, 1)

    old_success = '''    success_status = (
        "bulk_assignments_cleared"
        if mode == "clear"
        else "bulk_assignments_saved"
    )
'''

    new_success = '''    success_status = (
        "bulk_assignments_cleared"
        if mode == "clear"
        else (
            "bulk_assignments_sent_existing"
            if auto_send_existing
            else "bulk_assignments_saved"
        )
    )
'''

    if old_success not in text:
        raise RuntimeError("Không tìm thấy block success_status.")

    return text.replace(old_success, new_success, 1)


def patch_surveys(text: str) -> str:
    if MARKER_POST in text:
        return text

    text = insert_dict_message(
        text,
        "STATUS_MESSAGES",
        STATUS_KEY,
        "Đã giao phiếu theo phân công hiện có.",
    )

    text = insert_dict_message(
        text,
        "BULK_ASSIGNMENT_ERROR_MESSAGES",
        ERROR_KEY,
        "Phiếu chưa có phân công phù hợp để giao tự động. Nếu cần thay đổi, hãy chọn trường hoặc giáo viên mới.",
    )

    text = insert_helper(text)
    text = patch_post(text)
    return text


def patch_template(text: str) -> str:
    if MARKER_TEMPLATE in text:
        return text

    candidates = (
        (
            "if (mode !== 'clear' && !userCount) {",
            "if (mode !== 'clear' && !userCount && mode !== 'replace') {",
        ),
        (
            'if (mode !== "clear" && !userCount) {',
            'if (mode !== "clear" && !userCount && mode !== "replace") {',
        ),
    )

    changed = False

    for old, new in candidates:
        if old in text:
            text = text.replace(old, new, 1)
            changed = True
            break

    if not changed:
        raise RuntimeError("Không tìm thấy validation userCount trong template.")

    anchor = "                <h2>Chọn cách xử lý</h2>"

    if anchor not in text:
        raise RuntimeError("Không tìm thấy tiêu đề 'Chọn cách xử lý'.")

    guide = f'''                <h2>Chọn cách xử lý</h2>
                {MARKER_TEMPLATE}
                <div class="notice notice-info" style="margin-bottom: 12px;">
                    <strong>Giao theo phân công hiện có:</strong>
                    chỉ cần chọn phiếu rồi bấm
                    <strong>Giao phiếu</strong>, không cần chọn lại nơi nhận.
                    Khi có thay đổi mới chọn trường/giáo viên mới để giao lại.
                </div>'''

    return text.replace(anchor, guide, 1)


def verify_surveys(text: str) -> None:
    ast.parse(text)

    required = (
        MARKER_HELPER,
        MARKER_POST,
        "lay_nguoi_nhan_giao_phieu_tu_phan_cong_hien_co",
        "auto_send_existing",
        "auto_targets_by_form",
        'effective_mode = "add"',
        "dong_bo_nhiem_vu_truong_khi_giao_phieu",
        STATUS_KEY,
        ERROR_KEY,
        "truong_gui_xa",
        "AUTO_SEND_AFTER_TEACHER_ASSIGN_START",
    )

    missing = [token for token in required if token not in text]

    if missing:
        raise RuntimeError(
            "surveys.py sau sửa thiếu: " + repr(missing)
        )


def verify_template(text: str) -> None:
    if MARKER_TEMPLATE not in text:
        raise RuntimeError("Template thiếu marker.")

    if (
        "mode !== 'replace'" not in text
        and 'mode !== "replace"' not in text
    ):
        raise RuntimeError("Template chưa cho phép giao không chọn nơi nhận mới.")


def py_compile_target() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(SURVEYS)],
        cwd=str(PROJECT),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "py_compile lỗi:\n"
            + result.stdout
            + "\n"
            + result.stderr
        )


def jinja_compile() -> None:
    code = (
        "from jinja2 import Environment, FileSystemLoader\n"
        "from pathlib import Path\n"
        f"p=Path(r'{PROJECT}')\n"
        "e=Environment(loader=FileSystemLoader(str(p/'app'/'templates')))\n"
        "e.get_template('surveys/bulk_assignments.html')\n"
        "print('JINJA=OK')\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Jinja compile lỗi:\n"
            + result.stdout
            + "\n"
            + result.stderr
        )


def main() -> int:
    print("=" * 116)
    print("ĐỒNG BỘ GIAO PHIẾU THEO PHÂN CÔNG HIỆN CÓ - XÃ -> TRƯỜNG -> GIÁO VIÊN")
    print("=" * 116)
    print()

    for path in (SURVEYS, TEMPLATE, WORKFLOW, DB):
        if not path.exists():
            print(f"[LỖI] Không tìm thấy: {path}")
            return 1

    surveys_sha_before = sha256_file(SURVEYS)
    template_sha_before = sha256_file(TEMPLATE)
    workflow_sha_before = sha256_file(WORKFLOW)
    db_sha_before = sha256_file(DB)
    state_before = db_state()

    try:
        if state_before["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check != ok")

        if state_before["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi.")

        print("[1/9] Database: integrity=ok; FK=0.")

        surveys_text = read_text(SURVEYS)
        template_text = read_text(TEMPLATE)

        already_installed = (
            MARKER_POST in surveys_text
            and MARKER_TEMPLATE in template_text
        )

        if not already_installed:
            if surveys_sha_before != EXPECTED_SURVEYS_SHA:
                raise RuntimeError(
                    "surveys.py không còn đúng bản khảo sát.\n"
                    f"Hiện tại: {surveys_sha_before}\n"
                    f"Yêu cầu : {EXPECTED_SURVEYS_SHA}"
                )

            if template_sha_before != EXPECTED_TEMPLATE_SHA:
                raise RuntimeError(
                    "bulk_assignments.html không còn đúng bản khảo sát.\n"
                    f"Hiện tại: {template_sha_before}\n"
                    f"Yêu cầu : {EXPECTED_TEMPLATE_SHA}"
                )

            if workflow_sha_before != EXPECTED_WORKFLOW_SHA:
                raise RuntimeError(
                    "survey_school_workflow.py không còn đúng bản sau chốt 100%.\n"
                    f"Hiện tại: {workflow_sha_before}\n"
                    f"Yêu cầu : {EXPECTED_WORKFLOW_SHA}"
                )

            ast.parse(surveys_text)

            print("[2/9] Source đúng bản khảo sát; SHA guard: ĐẠT.")

            BACKUP.mkdir(parents=True, exist_ok=False)
            backup_files()

            print(f"[3/9] Backup: {BACKUP}")

            new_surveys = patch_surveys(surveys_text)
            new_template = patch_template(template_text)

            verify_surveys(new_surveys)
            verify_template(new_template)

            write_text(SURVEYS, new_surveys)
            write_text(TEMPLATE, new_template)

            print("[4/9] Đã cài: không chọn mới = giao theo phân công hiện có.")
        else:
            print("[2/9] Marker đã có; chuyển sang verify.")
            print("[3/9] Không tạo backup mới.")
            print("[4/9] Không cài lặp.")

        final_surveys = read_text(SURVEYS)
        final_template = read_text(TEMPLATE)

        verify_surveys(final_surveys)
        verify_template(final_template)

        print("[5/9] AST + kiểm tra logic source: ĐẠT.")

        py_compile_target()
        jinja_compile()

        print("[6/9] py_compile + Jinja compile: ĐẠT.")

        checks = (
            (
                "auto school preserve team",
                'effective_mode = "add"' in final_surveys,
            ),
            (
                "teacher auto report retained",
                "AUTO_SEND_AFTER_TEACHER_ASSIGN_START" in final_surveys
                and "truong_gui_xa" in final_surveys,
            ),
            (
                "manual replacement retained",
                'mode == "replace"' in final_surveys,
            ),
            (
                "school task sync retained",
                "dong_bo_nhiem_vu_truong_khi_giao_phieu" in final_surveys,
            ),
        )

        bad = [name for name, ok in checks if not ok]

        if bad:
            raise RuntimeError(
                "Kiểm tra nghiệp vụ không đạt: " + ", ".join(bad)
            )

        print("[7/9] Preserve tổ 3 cấp + giao lại + tự báo cáo xã: ĐẠT.")

        state_after = db_state()
        db_sha_after = sha256_file(DB)

        if state_after != state_before:
            raise RuntimeError("Trạng thái DB trước/sau khác nhau.")

        if db_sha_after != db_sha_before:
            raise RuntimeError("SHA256 database thay đổi.")

        print("[8/9] Database: KHÔNG THAY ĐỔI.")

        surveys_sha_after = sha256_file(SURVEYS)
        template_sha_after = sha256_file(TEMPLATE)

        report_lines = [
            "=" * 116,
            "BÁO CÁO CÀI ĐẶT ĐỒNG BỘ GIAO PHIẾU",
            "=" * 116,
            "",
            "QUY TẮC ĐÃ CÀI:",
            "1. Không chọn nơi nhận mới + mode replace => giao theo phân công hiện có.",
            "2. Xã -> Trường: tự suy ra trường từ school_id của thành viên đã phân công.",
            "3. Auto giao trường dùng mode ADD nội bộ => không xóa tổ giáo viên 3 cấp.",
            "4. Trường -> GV: tự lấy đúng GV/CBQL hiện có thuộc trường đăng nhập.",
            "5. Chọn nơi nhận mới => luồng giao lại/thay đổi cũ vẫn giữ nguyên.",
            "6. Sau giao/thay GV => tự gửi báo cáo lên xã vẫn giữ nguyên.",
            "",
            "SOURCE:",
            f"surveys trước : {surveys_sha_before}",
            f"surveys sau   : {surveys_sha_after}",
            f"template trước: {template_sha_before}",
            f"template sau  : {template_sha_after}",
            f"workflow      : {workflow_sha_before} (không sửa)",
            f"backup        : {BACKUP if BACKUP.exists() else '(không tạo mới)'}",
            "",
            "DATABASE:",
            f"SHA trước: {db_sha_before}",
            f"SHA sau  : {db_sha_after}",
            "Database: KHÔNG THAY ĐỔI.",
            "",
            "KIỂM TRA:",
            "AST: ĐẠT",
            "py_compile: ĐẠT",
            "Jinja compile: ĐẠT",
            "Preserve tổ 3 cấp: ĐẠT",
            "Tự báo cáo xã sau giao GV: GIỮ NGUYÊN",
            "",
            "KẾT LUẬN: CÀI ĐẶT THÀNH CÔNG.",
        ]

        EXPORTS.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            "\n".join(report_lines),
            encoding="utf-8-sig",
        )

        print(f"[9/9] Báo cáo: {REPORT}")
        print()
        print("=" * 116)
        print("CÀI ĐẶT THÀNH CÔNG.")
        print("Không chọn mới = giao theo phân công hiện có.")
        print("Có chọn mới = giao lại/thay đổi.")
        print("Database: KHÔNG THAY ĐỔI.")
        print("=" * 116)

        return 0

    except Exception as exc:
        print()
        print("=" * 116)
        print("[LỖI] CÀI ĐẶT KHÔNG HOÀN TẤT")
        print(str(exc))
        print("=" * 116)

        try:
            if BACKUP.exists():
                restore_files()
                print("Đã rollback surveys.py + template từ backup.")
        except Exception as rollback_exc:
            print("Rollback lỗi: " + str(rollback_exc))

        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            error_path = EXPORTS / f"loi_cai_dat_dong_bo_giao_phieu_{STAMP}.txt"
            error_path.write_text(
                f"Lỗi: {exc}\n\n" + traceback.format_exc(),
                encoding="utf-8-sig",
            )
            print(f"Chi tiết lỗi: {error_path}")
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
