from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
SURVEYS = APP / "routers" / "surveys.py"
WORKFLOW = APP / "routers" / "survey_school_workflow.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_8_2_{STAMP}"

WORKFLOW_FUNC = '@router.post("/{batch_id}/phan-cong-truong/gui-xa")\ndef truong_gui_xa(\n    request: Request,\n    batch_id: int,\n    notes: Annotated[str, Form()] = "",\n    db: Session = Depends(get_db),\n):\n    # === BAI_13B_11_8_2_SEND_TO_COMMUNE_START ===\n    actor = lay_nguoi_dung(request)\n    role_code = normalize_role_code(actor.get("role_code"))\n    batch = lay_dot(db, batch_id)\n    school_id = actor.get("school_id")\n\n    if (\n        batch is None\n        or role_code != SCHOOL_ROLE_CODE\n        or school_id is None\n    ):\n        return redirect_workflow(batch_id, "forbidden")\n\n    try:\n        school_id_int = int(school_id)\n    except (TypeError, ValueError):\n        return redirect_workflow(batch_id, "forbidden")\n\n    counts = dem_phieu_cua_truong(\n        db,\n        batch_id=batch.id,\n        school_id=school_id_int,\n    )\n\n    assignment = db.scalar(\n        select(SurveySchoolAssignment).where(\n            SurveySchoolAssignment.survey_batch_id == batch.id,\n            SurveySchoolAssignment.school_id == school_id_int,\n        )\n    )\n\n    if assignment is None:\n        if int(counts.get("form_total") or 0) <= 0:\n            return redirect_workflow(batch.id, "forbidden")\n\n        assignment = SurveySchoolAssignment(\n            survey_batch_id=batch.id,\n            school_id=school_id_int,\n            status="DANG_THUC_HIEN",\n            assigned_by_user_id=actor.get("id"),\n            assigned_at=datetime.now(),\n            notes=(\n                "Tự đồng bộ nhiệm vụ từ phiếu đã giao "\n                "(Bài 13B-11.8.2)."\n            ),\n        )\n        db.add(assignment)\n        db.flush()\n\n    if assignment.is_locked:\n        db.rollback()\n        return redirect_workflow(batch.id, "forbidden")\n\n    state = lay_trang_thai_dia_ban(db, batch)\n    if state.is_province_locked or state.is_commune_locked:\n        db.rollback()\n        return redirect_workflow(batch.id, "province_lock_blocks")\n\n    assignment.status = "DA_GUI_XA"\n    assignment.submitted_at = datetime.now()\n\n    ghi_nhat_ky(\n        db=db,\n        batch_id=batch.id,\n        school_id=school_id_int,\n        action="TRUONG_GUI_XA",\n        actor=actor,\n        reason=str(notes or "").strip(),\n        form_total=counts["form_total"],\n        completed_form_total=counts["completed_total"],\n    )\n\n    db.commit()\n    return redirect_workflow(batch.id, "school_submitted")\n    # === BAI_13B_11_8_2_SEND_TO_COMMUNE_END ===\n'
TEACHER_ROUTE = '@router.post("/{batch_id}/giao-phieu-giao-vien/luu")\nasync def luu_giao_phieu_cho_giao_vien(\n    batch_id: int,\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    # === BAI_13B_11_8_2_AUTO_SEND_AFTER_TEACHER_ASSIGN_START ===\n    response = await luu_phan_cong_v4_theo_cap(\n        batch_id=batch_id,\n        assignment_level="teacher",\n        request=request,\n        db=db,\n    )\n\n    location = str(response.headers.get("location") or "")\n    lower_location = location.lower()\n\n    assignment_saved = (\n        int(getattr(response, "status_code", 0) or 0) == 303\n        and "error=" not in lower_location\n        and "forbidden" not in lower_location\n        and "save_failed" not in lower_location\n        and "invalid" not in lower_location\n        and "not_found" not in lower_location\n        and (\n            "auto_print=1" in lower_location\n            or "?status=" in lower_location\n            or "&status=" in lower_location\n        )\n    )\n\n    if assignment_saved:\n        from app.routers.survey_school_workflow import truong_gui_xa\n\n        send_response = truong_gui_xa(\n            request=request,\n            batch_id=batch_id,\n            notes=(\n                "Tự động gửi lại báo cáo xã/phường "\n                "sau khi trường giao/thay giáo viên."\n            ),\n            db=db,\n        )\n\n        send_location = str(\n            send_response.headers.get("location") or ""\n        ).lower()\n\n        if "school_submitted" not in send_location:\n            return send_response\n\n    return response\n    # === BAI_13B_11_8_2_AUTO_SEND_AFTER_TEACHER_ASSIGN_END ===\n'

WF_START = "# === BAI_13B_11_8_2_SEND_TO_COMMUNE_START ==="
WF_END = "# === BAI_13B_11_8_2_SEND_TO_COMMUNE_END ==="
TR_START = "# === BAI_13B_11_8_2_AUTO_SEND_AFTER_TEACHER_ASSIGN_START ==="
TR_END = "# === BAI_13B_11_8_2_AUTO_SEND_AFTER_TEACHER_ASSIGN_END ==="


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_file(path: Path) -> None:
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, path)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def replace_function(
    text: str,
    function_name: str,
    replacement: str,
    required_markers: list[str],
) -> str:
    tree = ast.parse(text)
    target = None

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                target = node
                break

    if target is None:
        raise RuntimeError(f"Không tìm thấy hàm {function_name}.")

    start_line = target.lineno
    if target.decorator_list:
        start_line = min(d.lineno for d in target.decorator_list)
    end_line = target.end_lineno

    lines = text.splitlines(keepends=True)
    old_block = "".join(lines[start_line - 1:end_line])

    for marker in required_markers:
        if marker not in old_block:
            raise RuntimeError(
                f"Hàm {function_name} khác cấu trúc dự kiến, thiếu: {marker}"
            )

    return (
        "".join(lines[:start_line - 1])
        + replacement
        + "\n\n"
        + "".join(lines[end_line:])
    )


def patch_workflow() -> None:
    text = read_text(WORKFLOW)

    if WF_START in text:
        print(" - workflow đã có Bài 13B-11.8.2.")
        return

    # Nếu người dùng đã cài thử 13B-11.8.1 thì vẫn thay toàn bộ hàm
    # bằng phiên bản 13B-11.8.2.
    required = [
        '"/{batch_id}/phan-cong-truong/gui-xa"',
        "SurveySchoolAssignment",
        'assignment.status = "DA_GUI_XA"',
        'action="TRUONG_GUI_XA"',
    ]

    text = replace_function(
        text,
        "truong_gui_xa",
        WORKFLOW_FUNC,
        required,
    )
    write_text(WORKFLOW, text)


def patch_surveys() -> None:
    text = read_text(SURVEYS)

    if TR_START in text:
        print(" - surveys.py đã có Bài 13B-11.8.2.")
        return

    required = [
        '"/{batch_id}/giao-phieu-giao-vien/luu"',
        'assignment_level="teacher"',
        "luu_phan_cong_v4_theo_cap",
    ]

    text = replace_function(
        text,
        "luu_giao_phieu_cho_giao_vien",
        TEACHER_ROUTE,
        required,
    )
    write_text(SURVEYS, text)


def verify_file(path: Path, markers: list[str]) -> None:
    text = read_text(path)

    for marker in markers:
        if marker not in text:
            raise RuntimeError(
                f"Kiểm tra {path.name} thiếu marker: {marker}"
            )

    ast.parse(text)

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())

    if result.returncode != 0:
        raise RuntimeError(f"py_compile {path.name} không đạt.")


def main() -> int:
    print("=" * 112)
    print(
        "BÀI 13B-11.8.2 - THAY GIÁO VIÊN -> GIAO -> "
        "TỰ ĐỘNG GỬI BÁO CÁO XÃ"
    )
    print("=" * 112)
    print()
    print("LUỒNG SAU KHI CÀI:")
    print(" 1. Trường chọn giáo viên thay thế.")
    print(" 2. Bấm Giao.")
    print(" 3. Hệ thống lưu phân công giáo viên.")
    print(" 4. Nếu thiếu nhiệm vụ trường thì tự tạo từ phiếu đã có.")
    print(" 5. Tự chuyển trạng thái sang ĐÃ GỬI XÃ.")
    print(" 6. Ghi nhật ký TRUONG_GUI_XA.")
    print()
    print("GIỮ NGUYÊN:")
    print(" - Không mở quyền sang trường khác.")
    print(" - Không cho trường chưa có phiếu gửi xã.")
    print(" - Khóa trường/xã/tỉnh vẫn có hiệu lực.")
    print(" - Không sửa schema database.")
    print()

    if not SURVEYS.exists() or not WORKFLOW.exists():
        raise RuntimeError("Thiếu tệp source bắt buộc.")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(SURVEYS)
    backup_file(WORKFLOW)
    print("Backup source:", BACKUP)

    try:
        patch_workflow()
        patch_surveys()

        verify_file(
            WORKFLOW,
            [
                WF_START,
                WF_END,
                'status="DANG_THUC_HIEN"',
                'assignment.status = "DA_GUI_XA"',
                'action="TRUONG_GUI_XA"',
                "dem_phieu_cua_truong(",
            ],
        )

        verify_file(
            SURVEYS,
            [
                TR_START,
                TR_END,
                'assignment_level="teacher"',
                "from app.routers.survey_school_workflow import truong_gui_xa",
                '"school_submitted" not in send_location',
            ],
        )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - survey_school_workflow.py: OK")
        print(" - surveys.py: OK")
        print(" - AST / py_compile: OK")
        print(" - Database lúc cài: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.8.2 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore_file(SURVEYS)
        restore_file(WORKFLOW)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
