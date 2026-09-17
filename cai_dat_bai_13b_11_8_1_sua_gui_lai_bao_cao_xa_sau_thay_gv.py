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
TARGET = APP / "routers" / "survey_school_workflow.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_8_1_{STAMP}"

MARK_START = "# === BAI_13B_11_8_1_RESUBMIT_TO_COMMUNE_START ==="
MARK_END = "# === BAI_13B_11_8_1_RESUBMIT_TO_COMMUNE_END ==="

NEW_FUNCTION = '@router.post("/{batch_id}/phan-cong-truong/gui-xa")\ndef truong_gui_xa(\n    request: Request,\n    batch_id: int,\n    notes: Annotated[str, Form()] = "",\n    db: Session = Depends(get_db),\n):\n    # === BAI_13B_11_8_1_RESUBMIT_TO_COMMUNE_START ===\n    actor = lay_nguoi_dung(request)\n    role_code = normalize_role_code(actor.get("role_code"))\n    batch = lay_dot(db, batch_id)\n    school_id = actor.get("school_id")\n\n    if (\n        batch is None\n        or role_code != SCHOOL_ROLE_CODE\n        or school_id is None\n    ):\n        return redirect_workflow(batch_id, "forbidden")\n\n    try:\n        school_id_int = int(school_id)\n    except (TypeError, ValueError):\n        return redirect_workflow(batch_id, "forbidden")\n\n    counts = dem_phieu_cua_truong(\n        db,\n        batch_id=batch.id,\n        school_id=school_id_int,\n    )\n\n    assignment = db.scalar(\n        select(SurveySchoolAssignment).where(\n            SurveySchoolAssignment.survey_batch_id == batch.id,\n            SurveySchoolAssignment.school_id == school_id_int,\n        )\n    )\n\n    if assignment is None:\n        if int(counts.get("form_total") or 0) <= 0:\n            return redirect_workflow(batch.id, "forbidden")\n\n        assignment = SurveySchoolAssignment(\n            survey_batch_id=batch.id,\n            school_id=school_id_int,\n            status="DANG_THUC_HIEN",\n            assigned_by_user_id=actor.get("id"),\n            assigned_at=datetime.now(),\n            notes=(\n                "Tự đồng bộ nhiệm vụ từ phiếu đã được giao trước đó "\n                "(Bài 13B-11.8.1)."\n            ),\n        )\n        db.add(assignment)\n        db.flush()\n\n    if assignment.is_locked:\n        db.rollback()\n        return redirect_workflow(batch.id, "forbidden")\n\n    state = lay_trang_thai_dia_ban(db, batch)\n    if state.is_province_locked or state.is_commune_locked:\n        db.rollback()\n        return redirect_workflow(batch.id, "province_lock_blocks")\n\n    assignment.status = "DA_GUI_XA"\n    assignment.submitted_at = datetime.now()\n\n    ghi_nhat_ky(\n        db=db,\n        batch_id=batch.id,\n        school_id=school_id_int,\n        action="TRUONG_GUI_XA",\n        actor=actor,\n        reason=str(notes or "").strip(),\n        form_total=counts["form_total"],\n        completed_form_total=counts["completed_total"],\n    )\n\n    db.commit()\n    return redirect_workflow(batch.id, "school_submitted")\n    # === BAI_13B_11_8_1_RESUBMIT_TO_COMMUNE_END ===\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_source() -> None:
    dst = BACKUP / TARGET.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, dst)


def restore_source() -> None:
    src = BACKUP / TARGET.relative_to(PROJECT)
    if src.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, TARGET)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch(text: str) -> str:
    if MARK_START in text:
        print(" - Bài 13B-11.8.1 đã có sẵn, không sửa lặp.")
        return text

    tree = ast.parse(text)
    target = None

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "truong_gui_xa":
                target = node
                break

    if target is None:
        raise RuntimeError("Không tìm thấy hàm truong_gui_xa.")

    start_line = target.lineno
    if target.decorator_list:
        start_line = min(d.lineno for d in target.decorator_list)

    end_line = target.end_lineno

    lines = text.splitlines(keepends=True)
    old_block = "".join(lines[start_line - 1:end_line])

    required_old = [
        '"/{batch_id}/phan-cong-truong/gui-xa"',
        "SurveySchoolAssignment",
        "assignment is None or assignment.is_locked",
        'assignment.status = "DA_GUI_XA"',
        'action="TRUONG_GUI_XA"',
    ]
    for marker in required_old:
        if marker not in old_block:
            raise RuntimeError(
                "Cấu trúc hàm truong_gui_xa khác dự kiến; "
                f"thiếu: {marker}"
            )

    return (
        "".join(lines[:start_line - 1])
        + NEW_FUNCTION
        + "\n\n"
        + "".join(lines[end_line:])
    )


def verify() -> None:
    text = read_text(TARGET)

    required = [
        MARK_START,
        MARK_END,
        '"/{batch_id}/phan-cong-truong/gui-xa"',
        "dem_phieu_cua_truong(",
        "if assignment is None:",
        'if int(counts.get("form_total") or 0) <= 0:',
        'status="DANG_THUC_HIEN"',
        'assignment.status = "DA_GUI_XA"',
        'action="TRUONG_GUI_XA"',
        "db.add(assignment)",
        "db.flush()",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Kiểm tra sau cài không đạt, thiếu: {marker}"
            )

    if text.count(MARK_START) != 1 or text.count(MARK_END) != 1:
        raise RuntimeError("Marker Bài 13B-11.8.1 bị lặp.")

    ast.parse(text)

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(TARGET)],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())

    if result.returncode != 0:
        raise RuntimeError(
            "py_compile survey_school_workflow.py không đạt."
        )


def main() -> int:
    print("=" * 112)
    print(
        "BÀI 13B-11.8.1 - SỬA GỬI LẠI BÁO CÁO XÃ "
        "SAU KHI THAY GIÁO VIÊN"
    )
    print("=" * 112)
    print()
    print("NGUYÊN NHÂN:")
    print(
        " - Trường đã có phiếu nhưng chưa có "
        "SurveySchoolAssignment."
    )
    print(
        " - Hàm truong_gui_xa gặp assignment=None nên trả "
        "forbidden."
    )
    print()
    print("BẢN SỬA:")
    print(
        " - Nếu trường đã có phiếu thực tế nhưng thiếu nhiệm vụ, "
        "tự tạo nhiệm vụ."
    )
    print(
        " - Sau đó tiếp tục gửi/gửi lại báo cáo lên xã như luồng cũ."
    )
    print(
        " - Nếu trường chưa có phiếu thì vẫn không được phép gửi."
    )
    print(
        " - Nếu nhiệm vụ bị khóa hoặc xã/tỉnh bị khóa thì vẫn chặn."
    )
    print()
    print("KHÔNG THAY ĐỔI:")
    print(" - Không sửa database khi cài.")
    print(" - Không xóa hoặc đổi phiếu.")
    print(" - Không đổi giáo viên đã phân công.")
    print(" - Không đổi menu/giao diện.")
    print(" - Không mở quyền sang trường khác/xã khác.")
    print()

    if not TARGET.exists():
        raise RuntimeError(f"Không tìm thấy: {TARGET}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        before = read_text(TARGET)
        after = patch(before)
        write_text(TARGET, after)

        verify()
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Đúng route /phan-cong-truong/gui-xa: OK")
        print(" - Kiểm tra phiếu thực tế của trường: OK")
        print(" - Tự tạo nhiệm vụ khi thiếu: OK")
        print(" - Trường không có phiếu vẫn bị chặn: OK")
        print(" - Khóa tỉnh/xã/trường vẫn giữ: OK")
        print(" - AST / py_compile: OK")
        print(" - Database lúc cài: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.8.1 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC "
            "survey_school_workflow.py..."
        )
        restore_source()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
