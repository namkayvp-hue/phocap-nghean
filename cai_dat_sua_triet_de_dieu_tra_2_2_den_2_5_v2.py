from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
ACCESS = APP / "access_control.py"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_sua_triet_de_dieu_tra_2_2_2_5_v2_{STAMP}"

MARK_HELPERS = "FIX_SURVEY_WORKING_BATCH_SCOPE_V2_HELPERS_START"
MARK_CALL = "FIX_SURVEY_WORKING_BATCH_SCOPE_V2_CALL_START"
MARK_MENU = "FIX_SURVEY_WORKING_BATCH_SCOPE_V2_MENU_START"

HELPERS = '\n# === FIX_SURVEY_WORKING_BATCH_SCOPE_V2_HELPERS_START ===\ndef _pc_batch_in_account_scope(\n    *,\n    db,\n    auth_user: dict[str, Any],\n    batch_id: int,\n) -> bool:\n    """Kiểm tra một đợt có nằm trong phạm vi thực của tài khoản hay không."""\n    role_code = normalize_role_code(auth_user.get("role_code"))\n\n    if role_code in {*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE}:\n        exists = db.execute(\n            text(\n                "SELECT 1 FROM survey_batches "\n                "WHERE id = :batch_id LIMIT 1"\n            ),\n            {"batch_id": int(batch_id)},\n        ).scalar()\n        return exists is not None\n\n    if role_code == COMMUNE_ROLE_CODE:\n        commune_id = auth_user.get("commune_id")\n        if commune_id is None:\n            return False\n        allowed = db.execute(\n            text(\n                "SELECT 1 FROM survey_batches "\n                "WHERE id = :batch_id "\n                "AND commune_id = :commune_id "\n                "LIMIT 1"\n            ),\n            {\n                "batch_id": int(batch_id),\n                "commune_id": int(commune_id),\n            },\n        ).scalar()\n        return allowed is not None\n\n    if role_code == SCHOOL_ROLE_CODE:\n        school_id = auth_user.get("school_id")\n        if school_id is None:\n            return False\n        allowed = db.execute(\n            text(\n                """\n                SELECT 1\n                FROM survey_forms AS sf\n                JOIN survey_form_investigators AS sfi\n                    ON sfi.survey_form_id = sf.id\n                JOIN users AS assigned_user\n                    ON assigned_user.id = sfi.user_id\n                WHERE sf.survey_batch_id = :batch_id\n                  AND assigned_user.school_id = :school_id\n                  AND assigned_user.is_active = 1\n                LIMIT 1\n                """\n            ),\n            {\n                "batch_id": int(batch_id),\n                "school_id": int(school_id),\n            },\n        ).scalar()\n        return allowed is not None\n\n    if role_code == TEACHER_ROLE_CODE:\n        user_id = auth_user.get("id")\n        if user_id is None:\n            return False\n        allowed = db.execute(\n            text(\n                """\n                SELECT 1\n                FROM survey_forms AS sf\n                JOIN survey_form_investigators AS sfi\n                    ON sfi.survey_form_id = sf.id\n                WHERE sf.survey_batch_id = :batch_id\n                  AND sfi.user_id = :user_id\n                LIMIT 1\n                """\n            ),\n            {\n                "batch_id": int(batch_id),\n                "user_id": int(user_id),\n            },\n        ).scalar()\n        return allowed is not None\n\n    return False\n\n\ndef _pc_latest_batch_for_account(\n    *,\n    db,\n    auth_user: dict[str, Any],\n) -> int | None:\n    """\n    Tìm đợt làm việc mới nhất đúng phạm vi:\n    - Xã: đợt của chính xã.\n    - Trường: đợt đã có phiếu giao cho nhân sự của trường.\n    - Giáo viên: đợt đã có phiếu giao trực tiếp.\n    """\n    role_code = normalize_role_code(auth_user.get("role_code"))\n\n    if role_code in {*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE}:\n        value = db.execute(\n            text(\n                """\n                SELECT id\n                FROM survey_batches\n                ORDER BY\n                    school_year_id DESC,\n                    created_at DESC,\n                    id DESC\n                LIMIT 1\n                """\n            )\n        ).scalar()\n        return int(value) if value is not None else None\n\n    if role_code == COMMUNE_ROLE_CODE:\n        commune_id = auth_user.get("commune_id")\n        if commune_id is None:\n            return None\n        value = db.execute(\n            text(\n                """\n                SELECT id\n                FROM survey_batches\n                WHERE commune_id = :commune_id\n                ORDER BY\n                    school_year_id DESC,\n                    created_at DESC,\n                    id DESC\n                LIMIT 1\n                """\n            ),\n            {"commune_id": int(commune_id)},\n        ).scalar()\n        return int(value) if value is not None else None\n\n    if role_code == SCHOOL_ROLE_CODE:\n        school_id = auth_user.get("school_id")\n        if school_id is None:\n            return None\n        value = db.execute(\n            text(\n                """\n                SELECT DISTINCT sb.id\n                FROM survey_batches AS sb\n                JOIN survey_forms AS sf\n                    ON sf.survey_batch_id = sb.id\n                JOIN survey_form_investigators AS sfi\n                    ON sfi.survey_form_id = sf.id\n                JOIN users AS assigned_user\n                    ON assigned_user.id = sfi.user_id\n                WHERE assigned_user.school_id = :school_id\n                  AND assigned_user.is_active = 1\n                ORDER BY\n                    sb.school_year_id DESC,\n                    sb.created_at DESC,\n                    sb.id DESC\n                LIMIT 1\n                """\n            ),\n            {"school_id": int(school_id)},\n        ).scalar()\n        return int(value) if value is not None else None\n\n    if role_code == TEACHER_ROLE_CODE:\n        user_id = auth_user.get("id")\n        if user_id is None:\n            return None\n        value = db.execute(\n            text(\n                """\n                SELECT DISTINCT sb.id\n                FROM survey_batches AS sb\n                JOIN survey_forms AS sf\n                    ON sf.survey_batch_id = sb.id\n                JOIN survey_form_investigators AS sfi\n                    ON sfi.survey_form_id = sf.id\n                WHERE sfi.user_id = :user_id\n                ORDER BY\n                    sb.school_year_id DESC,\n                    sb.created_at DESC,\n                    sb.id DESC\n                LIMIT 1\n                """\n            ),\n            {"user_id": int(user_id)},\n        ).scalar()\n        return int(value) if value is not None else None\n\n    return None\n\n\ndef _pc_resolve_working_batch_id(\n    *,\n    db,\n    auth_user: dict[str, Any],\n    path: str,\n) -> int | None:\n    """\n    Nếu URL hiện tại đang ở một đợt hợp lệ thì giữ nguyên đợt đó.\n    Nếu URL không có đợt hoặc đang mang batch_id cũ/sai phạm vi,\n    dùng đợt mới nhất thuộc đúng phạm vi tài khoản.\n    """\n    normalized_path = path.rstrip("/") or "/"\n    match = re.match(\n        r"^/dieu-tra/(?P<batch_id>\\d+)(?:/|$)",\n        normalized_path,\n    )\n    if match is not None:\n        requested = int(match.group("batch_id"))\n        if _pc_batch_in_account_scope(\n            db=db,\n            auth_user=auth_user,\n            batch_id=requested,\n        ):\n            return requested\n\n    return _pc_latest_batch_for_account(\n        db=db,\n        auth_user=auth_user,\n    )\n\n\ndef _pc_scope_safe_redirect_url(\n    *,\n    db,\n    auth_user: dict[str, Any],\n    path: str,\n    method: str,\n    working_batch_id: int | None,\n    query_string: bytes | None,\n) -> str | None:\n    """\n    Sửa mọi link GET/HEAD bị giữ batch_id cũ cho nhóm 2.2–2.5.\n    Không bao giờ tự đổi đợt đối với POST/PUT/PATCH/DELETE.\n    """\n    if method not in SAFE_METHODS:\n        return None\n\n    role_code = normalize_role_code(auth_user.get("role_code"))\n    if role_code not in {\n        COMMUNE_ROLE_CODE,\n        SCHOOL_ROLE_CODE,\n        TEACHER_ROLE_CODE,\n    }:\n        return None\n\n    normalized_path = path.rstrip("/") or "/"\n    match = re.match(\n        r"^/dieu-tra/(?P<batch_id>\\d+)(?P<suffix>/.*)?$",\n        normalized_path,\n    )\n    if match is None:\n        return None\n\n    requested_batch_id = int(match.group("batch_id"))\n    if _pc_batch_in_account_scope(\n        db=db,\n        auth_user=auth_user,\n        batch_id=requested_batch_id,\n    ):\n        return None\n\n    # Không có đợt thuộc phạm vi: quay về Danh sách đợt thay vì forbidden.\n    if working_batch_id is None:\n        return "/dieu-tra"\n\n    suffix = match.group("suffix") or ""\n    target = f"/dieu-tra/{int(working_batch_id)}{suffix}"\n\n    raw_query = query_string or b""\n    if raw_query:\n        try:\n            query_text = raw_query.decode("latin-1")\n        except Exception:\n            query_text = ""\n        if query_text:\n            target = f"{target}?{query_text}"\n\n    return target\n# === FIX_SURVEY_WORKING_BATCH_SCOPE_V2_HELPERS_END ===\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup_file(path: Path) -> None:
    rel = path.relative_to(PROJECT)
    dst = BACKUP / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch_access(text_value: str) -> str:
    required = [
        "class AccessControlMiddleware:",
        'scope["auth_user"] = auth_user',
        "def _co_quyen_dieu_tra",
        "COMMUNE_ROLE_CODE",
        "SCHOOL_ROLE_CODE",
        "TEACHER_ROLE_CODE",
        "RedirectResponse",
        "SAFE_METHODS",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(
                f"access_control.py thiếu nền mã nguồn: {marker}"
            )

    if MARK_HELPERS not in text_value:
        class_anchor = "class AccessControlMiddleware:"
        pos = text_value.find(class_anchor)
        if pos < 0:
            raise RuntimeError("Không tìm thấy AccessControlMiddleware.")
        text_value = (
            text_value[:pos]
            + HELPERS.rstrip()
            + "\n\n\n"
            + text_value[pos:]
        )

    if MARK_CALL not in text_value:
        anchor = '            scope["auth_user"] = auth_user\n'
        if anchor not in text_value:
            raise RuntimeError(
                "Không tìm thấy điểm gán scope auth_user."
            )

        call_block = """
            # === FIX_SURVEY_WORKING_BATCH_SCOPE_V2_CALL_START ===
            # Xác định đợt làm việc theo đúng phạm vi tài khoản ở MỌI request.
            # Không dùng lại batch_id cũ của tài khoản vừa đăng nhập trước đó.
            working_batch_id = _pc_resolve_working_batch_id(
                db=db,
                auth_user=auth_user,
                path=path,
            )
            scope["menu_survey_batch_id"] = working_batch_id

            # Nếu một link GET/HEAD đang giữ batch_id cũ/sai địa bàn,
            # tự chuyển cùng chức năng sang đợt đúng phạm vi.
            scope_redirect_url = _pc_scope_safe_redirect_url(
                db=db,
                auth_user=auth_user,
                path=path,
                method=method,
                working_batch_id=working_batch_id,
                query_string=scope.get("query_string"),
            )
            if scope_redirect_url is not None:
                response = RedirectResponse(
                    url=scope_redirect_url,
                    status_code=303,
                )
                await response(scope, receive, send)
                return
            # === FIX_SURVEY_WORKING_BATCH_SCOPE_V2_CALL_END ===
"""
        text_value = text_value.replace(
            anchor,
            anchor + call_block,
            1,
        )

    return text_value


def survey_menu_segment(text_value: str) -> tuple[int, int, str]:
    start = text_value.find("2. Điều tra hộ dân")
    if start < 0:
        raise RuntimeError(
            "Không tìm thấy menu '2. Điều tra hộ dân'."
        )

    candidates = []
    for marker in (
        "3. Học sinh",
        "4. Đội ngũ",
        "CSVC",
        "5. Báo cáo",
    ):
        pos = text_value.find(marker, start + 1)
        if pos > start:
            candidates.append(pos)

    if not candidates:
        raise RuntimeError(
            "Không xác định được điểm kết thúc menu Điều tra hộ dân."
        )

    end = min(candidates)
    return start, end, text_value[start:end]


def patch_menu(text_value: str) -> str:
    if MARK_MENU in text_value:
        return text_value

    # Biến được middleware gán theo đúng Xã/Trường/Giáo viên hiện đăng nhập.
    setup = """{# === FIX_SURVEY_WORKING_BATCH_SCOPE_V2_MENU_START === #}
{% set pc_survey_batch_id = request.scope.get('menu_survey_batch_id') if request is defined else none %}
"""
    text_value = setup + text_value

    start, end, segment = survey_menu_segment(text_value)

    # Chỉ sửa URL có dạng /dieu-tra/<batch>/... bên trong menu số 2.
    # Các URL chung như /dieu-tra/cap-nhat-ho-dan vẫn giữ nguyên.
    pattern = re.compile(
        r'href="\/dieu-tra\/'
        r'(?P<batch>\d+|\{\{\s*[^"}]+?\s*\}\})'
        r'\/(?P<suffix>[^"]+)"'
    )

    replace_count = 0

    def repl(match: re.Match) -> str:
        nonlocal replace_count
        suffix = match.group("suffix")
        replace_count += 1
        return (
            'href="{% if pc_survey_batch_id %}'
            '/dieu-tra/{{ pc_survey_batch_id }}/'
            + suffix
            + '{% else %}/dieu-tra{% endif %}"'
        )

    new_segment = pattern.sub(repl, segment)

    # Hỗ trợ template dùng nháy đơn cho href.
    pattern_single = re.compile(
        r"href='\/dieu-tra\/"
        r"(?P<batch>\d+|\{\{\s*[^'}]+?\s*\}\})"
        r"\/(?P<suffix>[^']+)'"
    )

    def repl_single(match: re.Match) -> str:
        nonlocal replace_count
        suffix = match.group("suffix")
        replace_count += 1
        return (
            'href="{% if pc_survey_batch_id %}'
            '/dieu-tra/{{ pc_survey_batch_id }}/'
            + suffix
            + '{% else %}/dieu-tra{% endif %}"'
        )

    new_segment = pattern_single.sub(repl_single, new_segment)

    # Nếu nhãn "Đợt đang làm việc" đang dùng số/biến cũ thì đổi luôn.
    label_patterns = [
        re.compile(
            r"Đợt đang làm việc:\s*#\s*\d+"
        ),
        re.compile(
            r"Đợt đang làm việc:\s*#\s*"
            r"\{\{\s*[^}]+\s*\}\}"
        ),
    ]
    label_replacement = (
        "Đợt đang làm việc: "
        "{% if pc_survey_batch_id %}"
        "#{{ pc_survey_batch_id }}"
        "{% else %}Chưa có đợt phù hợp{% endif %}"
    )
    for label_pattern in label_patterns:
        new_segment = label_pattern.sub(
            label_replacement,
            new_segment,
            count=1,
        )

    if replace_count == 0:
        # Không dừng cài: middleware vẫn sửa triệt để mọi GET/HEAD có batch sai.
        # Ghi marker để tránh chèn lặp và giữ nguyên template nếu cấu trúc link
        # đang được tạo bằng cách khác.
        print(
            "CẢNH BÁO: Không thay trực tiếp được URL trong menu. "
            "Middleware vẫn tự chuyển batch sai về đúng phạm vi."
        )
    else:
        print(
            f"Đã chuẩn hóa {replace_count} link theo đợt làm việc của tài khoản."
        )

    return (
        text_value[:start]
        + new_segment
        + text_value[end:]
    )


def verify() -> None:
    access_text = read_text(ACCESS)
    menu_text = read_text(MENU)

    for marker in (
        MARK_HELPERS,
        MARK_CALL,
        'scope["menu_survey_batch_id"] = working_batch_id',
        "_pc_scope_safe_redirect_url",
        "_pc_batch_in_account_scope",
        "_pc_latest_batch_for_account",
    ):
        if marker not in access_text:
            raise RuntimeError(
                f"Kiểm tra access_control chưa đạt: {marker}"
            )

    if MARK_MENU not in menu_text:
        raise RuntimeError(
            "Menu chưa có marker bản sửa V2."
        )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ACCESS)],
        cwd=PROJECT,
        check=True,
    )

    from jinja2 import Environment
    Environment().parse(menu_text)


def print_diagnostic() -> None:
    print("")
    print("CHẨN ĐOÁN CƠ CHẾ MỚI:")
    print(
        " - Xã: ưu tiên đợt mới nhất đúng commune_id của tài khoản."
    )
    print(
        " - Trường: ưu tiên đợt mới nhất có phiếu giao cho nhân sự của trường."
    )
    print(
        " - Giáo viên: ưu tiên đợt mới nhất có phiếu giao trực tiếp."
    )
    print(
        " - Link cũ/sai batch chỉ tự chuyển đối với GET/HEAD; "
        "mọi thao tác ghi vẫn phải qua kiểm tra quyền gốc."
    )


def main() -> int:
    print("=" * 110)
    print("SỬA TRIỆT ĐỂ ĐIỀU TRA 2.2 -> 2.5 CHO XÃ / TRƯỜNG / GIÁO VIÊN - V2")
    print("=" * 110)
    print("")
    print("NGUYÊN NHÂN CHÍNH:")
    print(" - Menu đang giữ một batch_id cũ/chung (ví dụ #132) sau khi đổi tài khoản.")
    print(" - Middleware kiểm tra đúng phạm vi nên từ chối toàn bộ 2.2, 2.3, 2.4, 2.5")
    print("   khi batch_id đó không thuộc tài khoản hiện tại.")
    print("")
    print("BẢN V2 SỬA Ở GỐC:")
    print(" 1. Mỗi request tự xác định đợt làm việc đúng phạm vi tài khoản.")
    print(" 2. Menu 2.2-2.5 dùng đợt đó thay cho batch_id cũ.")
    print(" 3. GET/HEAD có batch_id sai được tự chuyển sang cùng chức năng ở đợt đúng.")
    print(" 4. Không nới quyền dữ liệu:")
    print("    - Xã chỉ xã mình.")
    print("    - Trường chỉ đợt có phiếu thuộc trường.")
    print("    - Giáo viên chỉ đợt có phiếu giao trực tiếp.")
    print(" 5. Quyền từng hộ và mọi POST/ghi dữ liệu vẫn giữ nguyên.")
    print("")
    print("KHÔNG THAY ĐỔI DATABASE HOẶC DỮ LIỆU ĐÃ NHẬP.")
    print("")

    for path in (ACCESS, MENU):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    for path in (ACCESS, MENU):
        backup_file(path)

    try:
        ACCESS.write_text(
            patch_access(read_text(ACCESS)),
            encoding="utf-8",
        )
        MENU.write_text(
            patch_menu(read_text(MENU)),
            encoding="utf-8",
        )

        verify()
        clear_cache()

        print("")
        print("CAI DAT SUA TRIET DE DIEU TRA 2.2-2.5 V2 THANH CONG")
        print("Backup:", BACKUP)
        print_diagnostic()
        print("")
        print("Hãy khởi động lại Uvicorn, đăng xuất/đăng nhập lại rồi Ctrl + F5.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore_file(ACCESS)
        restore_file(MENU)
        clear_cache()
        print("ĐÃ KHÔI PHỤC access_control.py và dropdown_menu_v1.html.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
