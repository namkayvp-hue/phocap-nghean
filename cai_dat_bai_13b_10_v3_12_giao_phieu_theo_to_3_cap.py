from __future__ import annotations

import py_compile
import re
import shutil
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
SURVEYS = PROJECT / "app" / "routers" / "surveys.py"
TEMPLATE = PROJECT / "app" / "templates" / "surveys" / "bulk_assignments.html"
EXPORTS = PROJECT / "exports"

MARKER_GET_START = "# === BAI_13B_10_V3_12_TEAM_SCOPE_GET_START ==="
MARKER_GET_END = "# === BAI_13B_10_V3_12_TEAM_SCOPE_GET_END ==="
MARKER_POST_START = "# === BAI_13B_10_V3_12_TEAM_SCOPE_POST_START ==="
MARKER_POST_END = "# === BAI_13B_10_V3_12_TEAM_SCOPE_POST_END ==="
MARKER_TEMPLATE = "{# === BAI_13B_10_V3_12_GIAO_PHIEU_TEAM === #}"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_files() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = EXPORTS / f"backup_bai_13b_10_v3_12_{stamp}"
    for src in (SURVEYS, TEMPLATE):
        rel = src.relative_to(PROJECT)
        dst = backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return backup


def restore(backup: Path) -> None:
    for src in (SURVEYS, TEMPLATE):
        rel = src.relative_to(PROJECT)
        saved = backup / rel
        if saved.exists():
            shutil.copy2(saved, src)


def function_block(text: str, func_name: str) -> tuple[int, int, str]:
    pattern = re.compile(
        rf"(?m)^(?:async\s+def|def)\s+{re.escape(func_name)}\s*\("
    )
    m = pattern.search(text)
    if not m:
        raise RuntimeError(f"Không tìm thấy hàm {func_name} trong surveys.py")

    start = m.start()
    next_def = re.search(r"(?m)^(?:async\s+def|def)\s+\w+\s*\(", text[m.end():])
    next_route = re.search(r"(?m)^@router\.", text[m.end():])

    candidates = []
    if next_def:
        candidates.append(m.end() + next_def.start())
    if next_route:
        candidates.append(m.end() + next_route.start())

    end = min(candidates) if candidates else len(text)
    return start, end, text[start:end]


def replace_in_function(text: str, func_name: str, old: str, new: str, marker: str) -> str:
    start, end, block = function_block(text, func_name)
    if marker in block:
        return text
    if old not in block:
        raise RuntimeError(
            f"Hàm {func_name} không giống source đã kiểm tra; không tìm thấy đoạn cần sửa."
        )
    block2 = block.replace(old, new, 1)
    return text[:start] + block2 + text[end:]


def patch_surveys(text: str) -> str:
    old_get = '''        base_scope_filters.append(
            dieu_kien_phieu_da_giao_truong(int(current_school_id))
        )'''
    new_get = f'''        {MARKER_GET_START}
        # V3.12: giữ tương thích giao trường V4 cũ, đồng thời nhận đúng
        # các phiếu tổ điều tra 3 cấp mà xã/phường đã chốt.
        base_scope_filters.append(
            or_(
                dieu_kien_phieu_da_giao_truong(int(current_school_id)),
                SurveyForm.investigators.any(
                    SurveyFormInvestigator.user.has(
                        User.school_id == int(current_school_id)
                    )
                ),
            )
        )
        {MARKER_GET_END}'''
    text = replace_in_function(
        text,
        "hien_thi_trang_phan_cong_v4",
        old_get,
        new_get,
        MARKER_GET_START,
    )

    old_post = '''        form_filters.append(
            dieu_kien_phieu_da_giao_truong(int(current_school_id))
        )'''
    new_post = f'''        {MARKER_POST_START}
        # V3.12: POST dùng cùng phạm vi với GET. Chỉ cho phép trường
        # thao tác phiếu có thành viên tổ thuộc chính school_id của mình.
        form_filters.append(
            or_(
                dieu_kien_phieu_da_giao_truong(int(current_school_id)),
                SurveyForm.investigators.any(
                    SurveyFormInvestigator.user.has(
                        User.school_id == int(current_school_id)
                    )
                ),
            )
        )
        {MARKER_POST_END}'''
    text = replace_in_function(
        text,
        "luu_phan_cong_v4_theo_cap",
        old_post,
        new_post,
        MARKER_POST_START,
    )
    return text


def patch_template(text: str) -> str:
    if MARKER_TEMPLATE in text:
        return text

    changed = False

    replacements = [
        (
            "“Giao lại” chỉ thay cán bộ, giáo viên của trường; nhiệm vụ xã giao cho trường vẫn được giữ nguyên.",
            "“Thay thế/điều chỉnh” chỉ thay cán bộ, giáo viên thuộc trường mình; phân công 3 cấp do xã/phường chốt và 2 giáo viên của các trường còn lại vẫn được giữ nguyên.",
        ),
        (
            "{% if assignment_level == 'school' %}Giao/chuyển trường{% else %}Giao lại{% endif %}",
            "{% if assignment_level == 'school' %}Giao/chuyển trường{% else %}Thay thế/điều chỉnh{% endif %}",
        ),
        (
            "{% if assignment_level == 'school' %}Giao phiếu cho trường{% else %}Giao phiếu cho giáo viên{% endif %}",
            "{% if assignment_level == 'school' %}Giao phiếu cho trường{% else %}📤 Giao phiếu{% endif %}",
        ),
    ]
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)
            changed = True

    anchor = '''                    <button class="button button-secondary" type="button" onclick="clearSelections()">
                        Bỏ chọn
                    </button>'''
    insert = f'''                    <button class="button button-secondary" type="button" onclick="clearSelections()">
                        Bỏ chọn
                    </button>
                    {{% if assignment_level == 'teacher' %}}
                        {MARKER_TEMPLATE}
                        <a
                            class="button button-secondary"
                            href="/dieu-tra/{{{{ batch.id }}}}/phan-cong-truong"
                            title="Mở nhiệm vụ trường để gửi/cập nhật kết quả về xã/phường"
                        >
                            📨 Gửi lại báo cáo cho xã/phường
                        </a>
                    {{% endif %}}'''
    if anchor in text:
        text = text.replace(anchor, insert, 1)
        changed = True
    else:
        raise RuntimeError(
            "Không tìm thấy nút 'Bỏ chọn' đúng cấu trúc trong bulk_assignments.html."
        )

    if not changed:
        raise RuntimeError("Template không có thay đổi nào được áp dụng.")
    return text


def verify(surveys_text: str, template_text: str) -> None:
    _, _, get_block = function_block(surveys_text, "hien_thi_trang_phan_cong_v4")
    _, _, post_block = function_block(surveys_text, "luu_phan_cong_v4_theo_cap")

    checks = [
        (MARKER_GET_START in get_block, "GET chưa có marker V3.12"),
        (MARKER_POST_START in post_block, "POST chưa có marker V3.12"),
        (
            "SurveyFormInvestigator.user.has(" in get_block
            and "User.school_id == int(current_school_id)" in get_block,
            "GET chưa có phạm vi tổ 3 cấp theo school_id",
        ),
        (
            "SurveyFormInvestigator.user.has(" in post_block
            and "User.school_id == int(current_school_id)" in post_block,
            "POST chưa có phạm vi tổ 3 cấp theo school_id",
        ),
        (
            "Thay thế/điều chỉnh" in template_text,
            "Template chưa đổi nhãn Thay thế/điều chỉnh",
        ),
        (
            "Gửi lại báo cáo cho xã/phường" in template_text,
            "Template chưa có nút gửi lại báo cáo xã/phường",
        ),
    ]
    failures = [msg for ok, msg in checks if not ok]
    if failures:
        raise RuntimeError("; ".join(failures))


def clear_pycache() -> None:
    for path in (PROJECT / "app").rglob("__pycache__"):
        try:
            shutil.rmtree(path)
        except Exception:
            pass


def main() -> None:
    print("=" * 72)
    print("BÀI 13B-10 V3.12 - GIAO PHIẾU THEO TỔ 3 CẤP")
    print("=" * 72)
    print(" - Trường thấy đủ phiếu có GV của trường trong tổ 3 cấp.")
    print(" - Giữ tương thích các phiếu giao trường V4 cũ.")
    print(" - Thay 'Giao lại' bằng 'Thay thế/điều chỉnh'.")
    print(" - Có nút mở luồng gửi lại báo cáo cho xã/phường.")
    print(" - KHÔNG sửa database, KHÔNG sửa tổ đã chốt.")

    for path in (SURVEYS, TEMPLATE):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy file: {path}")

    backup = backup_files()
    print(f"Backup: {backup}")

    try:
        s0 = read_text(SURVEYS)
        t0 = read_text(TEMPLATE)

        s1 = patch_surveys(s0)
        t1 = patch_template(t0)

        write_text(SURVEYS, s1)
        write_text(TEMPLATE, t1)

        py_compile.compile(str(SURVEYS), doraise=True)
        verify(read_text(SURVEYS), read_text(TEMPLATE))
        clear_pycache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - GET thấy tổ 3 cấp theo school_id: OK")
        print(" - POST cho phép điều chỉnh đúng phiếu đó: OK")
        print(" - Nhãn Thay thế/điều chỉnh: OK")
        print(" - Nút Gửi lại báo cáo cho xã/phường: OK")
        print()
        print("CÀI ĐẶT BÀI 13B-10 V3.12 THÀNH CÔNG")
        print("Hãy khởi động lại Uvicorn và Ctrl+F5.")
        print(f"Nếu cần quay lại, backup ở: {backup}")

    except Exception:
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore(backup)
        clear_pycache()
        print("ĐÃ KHÔI PHỤC SOURCE TRƯỚC V3.12.")
        print(f"Backup: {backup}")
        raise


if __name__ == "__main__":
    main()
