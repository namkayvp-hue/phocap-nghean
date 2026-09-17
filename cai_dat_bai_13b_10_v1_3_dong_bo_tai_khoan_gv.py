from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"

ROUTER = APP / "routers" / "survey_team_registration.py"
TEMPLATE = APP / "templates" / "survey_teams" / "school_participants.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v1_3_{STAMP}"

HELPER_MARK = "BAI_13B_10_V1_3_STAFF_TO_TEACHER_ACCOUNTS_START"
ROUTE_MARK = "BAI_13B_10_V1_3_SYNC_ROUTE_START"
TPL_MARK = "Tạo tài khoản GV còn thiếu + tải Excel mật khẩu"

HELPER_BLOCK = '\n# =========================================================\n# BAI_13B_10_V1_3_STAFF_TO_TEACHER_ACCOUNTS_START\n# Lấy GV đang làm việc từ hồ sơ Đội ngũ để đối chiếu tài khoản đăng nhập.\n# =========================================================\n\ndef _staff_teacher_rows_for_batch(\n    db: Session,\n    *,\n    school_id: int,\n    school_year_id: int,\n) -> list[dict[str, Any]]:\n    if (\n        not _table_exists(db, "staff_members")\n        or not _table_exists(db, "staff_year_records")\n        or not _table_exists(db, "school_years")\n    ):\n        return []\n\n    target_code = db.execute(\n        text(\n            """\n            SELECT code\n            FROM school_years\n            WHERE id = :school_year_id\n            LIMIT 1\n            """\n        ),\n        {"school_year_id": int(school_year_id)},\n    ).scalar()\n\n    target_match = re.search(r"(\\d{4})", str(target_code or ""))\n    target_start = int(target_match.group(1)) if target_match else 9999\n\n    rows = db.execute(\n        text(\n            """\n            SELECT\n                syr.id AS record_id,\n                sm.id AS staff_member_id,\n                sm.ministry_staff_code,\n                sm.code AS internal_staff_code,\n                sm.full_name,\n                sy.code AS source_year_code,\n                CAST(SUBSTR(sy.code, 1, 4) AS INTEGER) AS source_year_start\n            FROM staff_year_records AS syr\n            JOIN staff_members AS sm\n              ON sm.id = syr.staff_member_id\n            JOIN school_years AS sy\n              ON sy.id = syr.school_year_id\n            WHERE syr.school_id = :school_id\n              AND syr.is_active = 1\n              AND sm.is_active = 1\n              AND UPPER(syr.position_group) = \'GIAO_VIEN\'\n              AND UPPER(syr.status_code) = \'DANG_LAM_VIEC\'\n              AND CAST(SUBSTR(sy.code, 1, 4) AS INTEGER) <= :target_start\n            ORDER BY\n                sm.id,\n                source_year_start DESC,\n                syr.id DESC\n            """\n        ),\n        {\n            "school_id": int(school_id),\n            "target_start": int(target_start),\n        },\n    ).mappings().all()\n\n    # Mỗi người chỉ lấy bản ghi năm gần nhất, tránh trùng qua các năm học.\n    result: list[dict[str, Any]] = []\n    seen: set[int] = set()\n    for row in rows:\n        item = dict(row)\n        staff_member_id = int(item["staff_member_id"])\n        if staff_member_id in seen:\n            continue\n        seen.add(staff_member_id)\n        result.append(item)\n    return result\n\n\ndef _normalized_person_name(value: Any) -> str:\n    return _normalize(value)\n\n\ndef _teacher_account_matches(\n    db: Session,\n    *,\n    school_id: int,\n    staff_row: dict[str, Any],\n) -> tuple[str, dict[str, Any] | None]:\n    ministry_code = str(\n        staff_row.get("ministry_staff_code")\n        or staff_row.get("internal_staff_code")\n        or ""\n    ).strip()\n    expected_username = f"gv.{ministry_code}".lower() if ministry_code else ""\n\n    if expected_username:\n        row = db.execute(\n            text(\n                """\n                SELECT\n                    u.id, u.username, u.full_name, u.school_id,\n                    u.is_active, UPPER(r.code) AS role_code\n                FROM users AS u\n                JOIN roles AS r ON r.id = u.role_id\n                WHERE LOWER(u.username) = :username\n                LIMIT 1\n                """\n            ),\n            {"username": expected_username},\n        ).mappings().first()\n\n        if row is not None:\n            account = dict(row)\n            if (\n                str(account.get("role_code") or "") == TEACHER_ROLE_CODE\n                and int(account.get("school_id") or 0) == int(school_id)\n            ):\n                return (\n                    "ACTIVE" if int(account.get("is_active") or 0) == 1 else "LOCKED",\n                    account,\n                )\n            return "CONFLICT", account\n\n    # Hỗ trợ tài khoản GV đã tạo thủ công với username khác:\n    # chỉ tái sử dụng khi đúng trường, đúng vai trò, và họ tên khớp duy nhất.\n    candidates = db.execute(\n        text(\n            """\n            SELECT\n                u.id, u.username, u.full_name, u.school_id,\n                u.is_active, UPPER(r.code) AS role_code\n            FROM users AS u\n            JOIN roles AS r ON r.id = u.role_id\n            WHERE u.school_id = :school_id\n              AND UPPER(r.code) = :role_code\n            """\n        ),\n        {\n            "school_id": int(school_id),\n            "role_code": TEACHER_ROLE_CODE,\n        },\n    ).mappings().all()\n\n    target_name = _normalized_person_name(staff_row.get("full_name"))\n    name_matches = [\n        dict(row)\n        for row in candidates\n        if _normalized_person_name(row.get("full_name")) == target_name\n    ]\n    if len(name_matches) == 1:\n        account = name_matches[0]\n        return (\n            "ACTIVE" if int(account.get("is_active") or 0) == 1 else "LOCKED",\n            account,\n        )\n\n    return "MISSING", None\n\n\ndef _safe_teacher_username(\n    db: Session,\n    *,\n    code: str,\n) -> str:\n    clean_code = re.sub(\n        r"[^a-zA-Z0-9_-]+",\n        "",\n        str(code or "").strip(),\n    ).lower()\n    if not clean_code:\n        clean_code = "khongma"\n\n    base = f"gv.{clean_code}"[:100]\n    candidate = base\n    index = 2\n\n    while db.execute(\n        text(\n            """\n            SELECT 1\n            FROM users\n            WHERE LOWER(username) = :username\n            LIMIT 1\n            """\n        ),\n        {"username": candidate.lower()},\n    ).scalar() is not None:\n        suffix = f".{index}"\n        candidate = f"{base[:100-len(suffix)]}{suffix}"\n        index += 1\n\n    return candidate\n\n\ndef _temporary_teacher_password() -> str:\n    import secrets\n\n    upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"\n    lower = "abcdefghijkmnopqrstuvwxyz"\n    digits = "23456789"\n    symbols = "@#$%"\n    required = [\n        secrets.choice(upper),\n        secrets.choice(lower),\n        secrets.choice(digits),\n        secrets.choice(symbols),\n    ]\n    alphabet = upper + lower + digits + symbols\n    required.extend(secrets.choice(alphabet) for _ in range(8))\n    secrets.SystemRandom().shuffle(required)\n    return "".join(required)\n\n# BAI_13B_10_V1_3_STAFF_TO_TEACHER_ACCOUNTS_END\n'
SYNC_ROUTE = '\n# =========================================================\n# BAI_13B_10_V1_3_SYNC_ROUTE_START\n# Trường chủ động tạo tài khoản GV còn thiếu từ hồ sơ Đội ngũ.\n# POST trả về Excel mật khẩu tạm; không lưu mật khẩu rõ trong CSDL.\n# =========================================================\n\n@router.post("/giao-vien-tham-gia/dong-bo-tai-khoan")\nasync def sync_teacher_accounts_from_staff(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != SCHOOL_ROLE_CODE:\n        return _forbidden()\n\n    _ensure_schema(db)\n\n    form = await request.form()\n    try:\n        batch_id = int(form.get("batch_id") or 0)\n    except (TypeError, ValueError):\n        batch_id = 0\n\n    school, batch = _validate_school_scope(\n        db,\n        request,\n        batch_id,\n    )\n    if school is None or batch is None:\n        return _forbidden()\n\n    # Nếu trường đã gửi danh sách về xã thì không tạo thêm trong bước này,\n    # tránh làm người dùng hiểu rằng danh sách đã gửi tự thay đổi.\n    submission = _submission(\n        db,\n        batch_id=batch_id,\n        school_id=int(school["id"]),\n    )\n    if submission is not None and submission.get("status") == "SENT":\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia"\n                f"?batch_id={batch_id}"\n            ),\n            status_code=303,\n        )\n\n    staff_rows = _staff_teacher_rows_for_batch(\n        db,\n        school_id=int(school["id"]),\n        school_year_id=int(batch["school_year_id"]),\n    )\n    if not staff_rows:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia"\n                f"?batch_id={batch_id}&status=no_staff"\n            ),\n            status_code=303,\n        )\n\n    teacher_role_id = db.execute(\n        text(\n            """\n            SELECT id\n            FROM roles\n            WHERE UPPER(code) = :role_code\n            LIMIT 1\n            """\n        ),\n        {"role_code": TEACHER_ROLE_CODE},\n    ).scalar()\n    if teacher_role_id is None:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia"\n                f"?batch_id={batch_id}&status=no_teacher_role"\n            ),\n            status_code=303,\n        )\n\n    from app.security import ma_hoa_mat_khau\n\n    created: list[dict[str, Any]] = []\n    reused: list[dict[str, Any]] = []\n    locked: list[dict[str, Any]] = []\n    conflicts: list[dict[str, Any]] = []\n\n    now_value = datetime.now().isoformat(\n        sep=" ",\n        timespec="seconds",\n    )\n\n    try:\n        for staff_row in staff_rows:\n            state, account = _teacher_account_matches(\n                db,\n                school_id=int(school["id"]),\n                staff_row=staff_row,\n            )\n\n            base_info = {\n                "full_name": str(staff_row.get("full_name") or ""),\n                "staff_code": str(\n                    staff_row.get("ministry_staff_code")\n                    or staff_row.get("internal_staff_code")\n                    or ""\n                ),\n                "source_year": str(staff_row.get("source_year_code") or ""),\n            }\n\n            if state == "ACTIVE" and account is not None:\n                reused.append({\n                    **base_info,\n                    "username": str(account.get("username") or ""),\n                    "note": "Tài khoản đang hoạt động - giữ nguyên mật khẩu.",\n                })\n                continue\n\n            if state == "LOCKED" and account is not None:\n                locked.append({\n                    **base_info,\n                    "username": str(account.get("username") or ""),\n                    "note": (\n                        "Tài khoản đang khóa - hệ thống KHÔNG tự mở khóa. "\n                        "Trường cần kiểm tra trước khi sử dụng."\n                    ),\n                })\n                continue\n\n            if state == "CONFLICT" and account is not None:\n                conflicts.append({\n                    **base_info,\n                    "username": str(account.get("username") or ""),\n                    "note": (\n                        "Tên đăng nhập theo mã giáo viên đã thuộc tài khoản "\n                        "khác trường/vai trò - KHÔNG tự sửa."\n                    ),\n                })\n                continue\n\n            password = _temporary_teacher_password()\n            username = _safe_teacher_username(\n                db,\n                code=base_info["staff_code"],\n            )\n\n            db.execute(\n                text(\n                    """\n                    INSERT INTO users (\n                        username,\n                        password_hash,\n                        full_name,\n                        role_id,\n                        commune_id,\n                        school_id,\n                        is_active,\n                        created_at\n                    ) VALUES (\n                        :username,\n                        :password_hash,\n                        :full_name,\n                        :role_id,\n                        :commune_id,\n                        :school_id,\n                        1,\n                        :created_at\n                    )\n                    """\n                ),\n                {\n                    "username": username,\n                    "password_hash": ma_hoa_mat_khau(password),\n                    "full_name": base_info["full_name"],\n                    "role_id": int(teacher_role_id),\n                    "commune_id": int(school["commune_id"]),\n                    "school_id": int(school["id"]),\n                    "created_at": now_value,\n                },\n            )\n\n            created.append({\n                **base_info,\n                "username": username,\n                "temporary_password": password,\n                "note": "Tài khoản mới - đổi mật khẩu sau khi bàn giao.",\n            })\n\n        # Chuẩn bị file bàn giao TRƯỚC commit để nếu tạo Excel lỗi\n        # thì toàn bộ INSERT còn có thể rollback.\n        from io import BytesIO\n        from openpyxl import Workbook\n        from openpyxl.styles import Font, Alignment\n        from fastapi.responses import StreamingResponse\n\n        workbook = Workbook()\n        ws = workbook.active\n        ws.title = "Tai_khoan_moi"\n\n        headers = [\n            "STT",\n            "Họ và tên",\n            "Mã cán bộ/GV",\n            "Tên đăng nhập",\n            "Mật khẩu tạm",\n            "Trường",\n            "Cấp học",\n            "Nguồn đội ngũ",\n            "Ghi chú",\n        ]\n        ws.append(headers)\n        for cell in ws[1]:\n            cell.font = Font(bold=True)\n            cell.alignment = Alignment(\n                horizontal="center",\n                vertical="center",\n                wrap_text=True,\n            )\n\n        level_code = _school_level(\n            db,\n            school_id=int(school["id"]),\n            school_name=str(school["name"]),\n            school_year_id=int(batch["school_year_id"]),\n        )\n        level_label = LEVEL_LABELS.get(level_code, level_code)\n\n        for index, item in enumerate(created, start=1):\n            ws.append([\n                index,\n                item["full_name"],\n                item["staff_code"],\n                item["username"],\n                item["temporary_password"],\n                school["name"],\n                level_label,\n                item["source_year"],\n                item["note"],\n            ])\n\n        if not created:\n            ws.append([\n                "",\n                "Không tạo tài khoản mới.",\n                "",\n                "",\n                "",\n                school["name"],\n                level_label,\n                "",\n                "Các tài khoản phù hợp đã tồn tại hoặc cần kiểm tra xung đột/khóa.",\n            ])\n\n        def add_status_sheet(title: str, rows: list[dict[str, Any]]) -> None:\n            sheet = workbook.create_sheet(title)\n            sheet.append([\n                "STT",\n                "Họ và tên",\n                "Mã cán bộ/GV",\n                "Tên đăng nhập",\n                "Nguồn đội ngũ",\n                "Ghi chú",\n            ])\n            for cell in sheet[1]:\n                cell.font = Font(bold=True)\n                cell.alignment = Alignment(\n                    horizontal="center",\n                    vertical="center",\n                    wrap_text=True,\n                )\n            for index, item in enumerate(rows, start=1):\n                sheet.append([\n                    index,\n                    item["full_name"],\n                    item["staff_code"],\n                    item["username"],\n                    item["source_year"],\n                    item["note"],\n                ])\n            if not rows:\n                sheet.append(["", "Không có", "", "", "", ""])\n\n            for width, col in zip(\n                [8, 28, 20, 26, 18, 55],\n                "ABCDEF",\n            ):\n                sheet.column_dimensions[col].width = width\n\n        add_status_sheet("Da_co_tai_khoan", reused)\n        add_status_sheet("Tai_khoan_dang_khoa", locked)\n        add_status_sheet("Can_kiem_tra", conflicts)\n\n        for width, col in zip(\n            [8, 28, 20, 26, 22, 34, 15, 18, 50],\n            "ABCDEFGHI",\n        ):\n            ws.column_dimensions[col].width = width\n\n        ws.freeze_panes = "A2"\n        for sheet in workbook.worksheets:\n            sheet.freeze_panes = "A2"\n\n        buffer = BytesIO()\n        workbook.save(buffer)\n        buffer.seek(0)\n\n        db.commit()\n\n    except Exception:\n        db.rollback()\n        raise\n\n    # Không ghi mật khẩu rõ xuống file hệ thống hoặc database.\n    safe_school = re.sub(\n        r"[^A-Za-z0-9_-]+",\n        "_",\n        _normalize(school["name"]).replace(" ", "_"),\n    ).strip("_") or f"school_{school[\'id\']}"\n    filename = (\n        f"tai_khoan_giao_vien_{safe_school}_"\n        f"{datetime.now().strftime(\'%Y%m%d_%H%M%S\')}.xlsx"\n    )\n\n    return StreamingResponse(\n        buffer,\n        media_type=(\n            "application/vnd.openxmlformats-officedocument."\n            "spreadsheetml.sheet"\n        ),\n        headers={\n            "Content-Disposition": (\n                f\'attachment; filename="{filename}"\'\n            )\n        },\n    )\n\n# BAI_13B_10_V1_3_SYNC_ROUTE_END\n'
TEMPLATE_BLOCK = '\n{% if staff_teacher_count > teachers|length and (not submission or submission.status != \'SENT\') %}\n<div class="notice-warn" style="margin:14px 0">\n    <strong>Hồ sơ Đội ngũ đã có {{ staff_teacher_count }} giáo viên đang làm việc,\n    nhưng mới có {{ teachers|length }} tài khoản giáo viên hoạt động.</strong>\n    <div style="margin-top:6px">\n        Để giáo viên xuất hiện trong danh sách tích chọn và sau này đăng nhập điện thoại,\n        cần tạo tài khoản GIAO_VIEN cho các hồ sơ còn thiếu.\n    </div>\n    <form\n        method="post"\n        action="/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia/dong-bo-tai-khoan"\n        target="_blank"\n        style="margin-top:12px"\n    >\n        <input type="hidden" name="batch_id" value="{{ batch.id }}">\n        <button\n            class="button button-primary"\n            type="submit"\n            onclick="return confirm(\'Tạo tài khoản giáo viên còn thiếu từ danh sách Đội ngũ và tải Excel mật khẩu tạm? Tài khoản đã có sẽ được giữ nguyên.\');"\n        >\n            🔄 Tạo tài khoản GV còn thiếu + tải Excel mật khẩu\n        </button>\n        <a\n            class="button button-secondary"\n            href="/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia?batch_id={{ batch.id }}"\n            style="margin-left:8px"\n        >\n            Làm mới danh sách sau khi đồng bộ\n        </a>\n    </form>\n</div>\n{% endif %}\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup_file(path: Path) -> None:
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)


def database_path() -> Path | None:
    sys.path.insert(0, str(PROJECT))
    old_cwd = Path.cwd()
    try:
        os.chdir(PROJECT)
        from app.database import DATABASE_PATH
        return Path(DATABASE_PATH)
    except Exception:
        return None
    finally:
        os.chdir(old_cwd)
        try:
            sys.path.remove(str(PROJECT))
        except ValueError:
            pass


def patch_router(text_value: str) -> str:
    if HELPER_MARK not in text_value:
        anchor = "\ndef _submission(\n"
        pos = text_value.find(anchor)
        if pos < 0:
            raise RuntimeError(
                "Không tìm thấy điểm chèn helper trước def _submission()."
            )
        text_value = (
            text_value[:pos]
            + "\n\n"
            + HELPER_BLOCK.strip()
            + "\n\n"
            + text_value[pos:]
        )

    # Bổ sung staff_teacher_count vào trang GET.
    if '"staff_teacher_count": len(staff_teachers)' not in text_value:
        anchor = "    teachers = _teacher_rows(db, school_id=int(school_id))\n"
        if anchor not in text_value:
            raise RuntimeError(
                "Không tìm thấy dòng lấy teachers trong school_participants_page."
            )
        replacement = (
            anchor
            + "    staff_teachers: list[dict[str, Any]] = []\n"
            + "    if batch is not None:\n"
            + "        staff_teachers = _staff_teacher_rows_for_batch(\n"
            + "            db,\n"
            + "            school_id=int(school_id),\n"
            + "            school_year_id=int(batch[\"school_year_id\"]),\n"
            + "        )\n"
        )
        text_value = text_value.replace(anchor, replacement, 1)

        context_anchor = '            "teachers": teachers,\n'
        if context_anchor not in text_value:
            raise RuntimeError(
                "Không tìm thấy context teachers của school_participants.html."
            )
        text_value = text_value.replace(
            context_anchor,
            context_anchor
            + '            "staff_teacher_count": len(staff_teachers),\n',
            1,
        )

    # Thông báo phụ nếu không có hồ sơ nguồn / vai trò GV.
    if '"no_staff":' not in text_value:
        msg_anchor = (
            '        "withdrawn": "Đã thu hồi danh sách để trường tiếp tục chỉnh sửa.",\n'
        )
        if msg_anchor not in text_value:
            raise RuntimeError(
                "Không tìm thấy status_messages của trang giáo viên tham gia."
            )
        text_value = text_value.replace(
            msg_anchor,
            msg_anchor
            + '        "no_staff": "Không tìm thấy hồ sơ giáo viên đang làm việc trong dữ liệu Đội ngũ.",\n'
            + '        "no_teacher_role": "Hệ thống chưa có vai trò GIAO_VIEN để tạo tài khoản.",\n',
            1,
        )

    if ROUTE_MARK not in text_value:
        route_anchor = '\n@router.post("/giao-vien-tham-gia/luu")\n'
        pos = text_value.find(route_anchor)
        if pos < 0:
            raise RuntimeError(
                "Không tìm thấy route /giao-vien-tham-gia/luu."
            )
        text_value = (
            text_value[:pos]
            + "\n\n"
            + SYNC_ROUTE.strip()
            + "\n\n"
            + text_value[pos:]
        )

    return text_value


def patch_template(text_value: str) -> str:
    if TPL_MARK in text_value:
        return text_value

    anchor = (
        "<p>Chọn giáo viên tham gia điều tra. "
        "Sang V2, xã/phường sẽ ghép tổ 1 MN + 1 TH + 1 THCS.</p>"
    )
    if anchor not in text_value:
        raise RuntimeError(
            "Không tìm thấy mô tả chọn giáo viên trong school_participants.html."
        )
    return text_value.replace(
        anchor,
        anchor + "\n" + TEMPLATE_BLOCK.strip(),
        1,
    )


def verify() -> None:
    router_text = read_text(ROUTER)
    template_text = read_text(TEMPLATE)

    required_router = [
        HELPER_MARK,
        ROUTE_MARK,
        '@router.post("/giao-vien-tham-gia/dong-bo-tai-khoan")',
        "_staff_teacher_rows_for_batch",
        '"staff_teacher_count": len(staff_teachers)',
        "ma_hoa_mat_khau",
        "StreamingResponse",
        "Workbook",
    ]
    for marker in required_router:
        if marker not in router_text:
            raise RuntimeError(
                f"Kiểm tra router chưa đạt: {marker}"
            )

    required_tpl = [
        TPL_MARK,
        "staff_teacher_count > teachers|length",
        "/giao-vien-tham-gia/dong-bo-tai-khoan",
        "Làm mới danh sách sau khi đồng bộ",
    ]
    for marker in required_tpl:
        if marker not in template_text:
            raise RuntimeError(
                f"Kiểm tra template chưa đạt: {marker}"
            )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )

    from jinja2 import Environment, FileSystemLoader
    env = Environment(
        loader=FileSystemLoader(str(APP / "templates"))
    )
    env.get_template("survey_teams/school_participants.html")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 112)
    print("BÀI 13B-10 V1.3 - ĐỒNG BỘ TÀI KHOẢN GV TỪ DANH SÁCH ĐỘI NGŨ")
    print("=" * 112)
    print("")
    print("NGUYÊN NHÂN ĐÃ XÁC ĐỊNH:")
    print(" - Danh sách Đội ngũ TH/THCS đã có giáo viên.")
    print(" - Nhưng 2.2.7 chỉ lấy tài khoản users có role GIAO_VIEN, school_id đúng trường, is_active=1.")
    print(" - Vì TH/THCS chưa có các tài khoản đó nên màn hình hiện GV đang hoạt động = 0.")
    print("")
    print("V1.3 BỔ SUNG:")
    print(" - Nút tạo tài khoản GV còn thiếu từ chính danh sách Đội ngũ.")
    print(" - Username ưu tiên gv.<Mã cán bộ/GV Bộ GD&ĐT>.")
    print(" - Tài khoản đã tồn tại: KHÔNG đổi mật khẩu, KHÔNG tạo trùng.")
    print(" - Tài khoản đang khóa: KHÔNG tự mở khóa.")
    print(" - Xung đột username/trường/vai trò: KHÔNG tự sửa.")
    print(" - Tài khoản mới nhận mật khẩu ngẫu nhiên 12 ký tự.")
    print(" - Mật khẩu tạm chỉ xuất trực tiếp ra Excel tải về; KHÔNG lưu rõ trong database/file server.")
    print("")
    print("KHÔNG SỬA dữ liệu Đội ngũ và không thay đổi các tài khoản đã có.")
    print("")

    for path in (ROUTER, TEMPLATE):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER)
    backup_file(TEMPLATE)

    db_path = database_path()
    if db_path is not None and db_path.exists():
        db_backup = BACKUP / "database" / db_path.name
        db_backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path, db_backup)

    try:
        ROUTER.write_text(
            patch_router(read_text(ROUTER)),
            encoding="utf-8",
        )
        TEMPLATE.write_text(
            patch_template(read_text(TEMPLATE)),
            encoding="utf-8",
        )

        verify()
        clear_cache()

        print("")
        print("CAI DAT BAI 13B-10 V1.3 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("SAU KHI KHỞI ĐỘNG LẠI:")
        print(" 1. Trường TH/THCS -> 2.2.7 Giáo viên tham gia điều tra.")
        print(" 2. Bấm 'Tạo tài khoản GV còn thiếu + tải Excel mật khẩu'.")
        print(" 3. Lưu file Excel bàn giao mật khẩu.")
        print(" 4. Quay lại trang và bấm 'Làm mới danh sách sau khi đồng bộ'.")
        print(" 5. Giáo viên phải xuất hiện để tích chọn và gửi xã/phường.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore_file(ROUTER)
        restore_file(TEMPLATE)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE TRƯỚC V1.3.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
