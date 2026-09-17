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
BUILDER = APP / "templates" / "survey_teams" / "commune_team_builder.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v3_1_{STAMP}"

ROUTE_MARK = "BAI_13B_10_V3_1_FINALIZE_SEND_START"
BUTTON_MARK = "BAI_13B_10_V3_1_FINALIZE_BUTTON_START"

ROUTE_BLOCK = '\n# =========================================================\n# BAI_13B_10_V3_1_FINALIZE_SEND_START\n# Chốt dự thảo tổ 3 cấp -> ghi chính thức vào survey_form_investigators.\n# Sau bước này Trường/Giáo viên nhìn thấy đợt và phiếu được giao.\n# =========================================================\n\n@router.post("/lap-to/chot-gui")\nasync def finalize_and_send_team_assignments_v3_1(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n\n    _ensure_schema(db)\n    _ensure_team_schema(db)\n\n    form = await request.form()\n    try:\n        batch_id = int(form.get("batch_id") or 0)\n    except (TypeError, ValueError):\n        batch_id = 0\n\n    batch = _commune_batch_scope(\n        db,\n        request,\n        batch_id,\n    )\n    if batch is None:\n        return _forbidden()\n\n    teams = [\n        dict(row)\n        for row in db.execute(\n            text(\n                """\n                SELECT\n                    id,\n                    team_number,\n                    status,\n                    generation_code\n                FROM survey_investigation_teams\n                WHERE survey_batch_id = :batch_id\n                ORDER BY team_number\n                """\n            ),\n            {"batch_id": int(batch_id)},\n        ).mappings().all()\n    ]\n\n    if not teams:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n                f"?batch_id={batch_id}&status=no_draft"\n            ),\n            status_code=303,\n        )\n\n    if any(str(row.get("status") or "") != "DRAFT" for row in teams):\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n                f"?batch_id={batch_id}&status=already_sent"\n            ),\n            status_code=303,\n        )\n\n    now_value = datetime.now().isoformat(\n        sep=" ",\n        timespec="seconds",\n    )\n\n    total_forms = 0\n    total_assignments = 0\n\n    try:\n        for team_row in teams:\n            team_id = int(team_row["id"])\n            team_number = int(team_row["team_number"])\n\n            members = [\n                dict(row)\n                for row in db.execute(\n                    text(\n                        """\n                        SELECT\n                            tm.user_id,\n                            tm.level_code,\n                            tm.order_number,\n                            tm.school_id,\n                            u.full_name,\n                            u.is_active\n                        FROM survey_investigation_team_members AS tm\n                        JOIN users AS u\n                          ON u.id = tm.user_id\n                        WHERE tm.team_id = :team_id\n                        ORDER BY tm.order_number\n                        """\n                    ),\n                    {"team_id": team_id},\n                ).mappings().all()\n            ]\n\n            member_levels = {\n                str(row.get("level_code") or "")\n                for row in members\n            }\n\n            if (\n                len(members) != 3\n                or member_levels != {"MN", "TH", "THCS"}\n                or any(int(row.get("is_active") or 0) != 1 for row in members)\n            ):\n                raise RuntimeError(\n                    f"Tổ {team_number} không đủ đúng 3 GV hoạt động "\n                    "MN + TH + THCS."\n                )\n\n            team_forms = [\n                dict(row)\n                for row in db.execute(\n                    text(\n                        """\n                        SELECT\n                            tf.survey_form_id,\n                            tf.assignment_order\n                        FROM survey_investigation_team_forms AS tf\n                        WHERE tf.team_id = :team_id\n                        ORDER BY tf.assignment_order\n                        """\n                    ),\n                    {"team_id": team_id},\n                ).mappings().all()\n            ]\n\n            if not team_forms:\n                raise RuntimeError(\n                    f"Tổ {team_number} không có hộ/phiếu; không được chốt."\n                )\n\n            for form_row in team_forms:\n                survey_form_id = int(form_row["survey_form_id"])\n\n                form_batch_id = db.execute(\n                    text(\n                        """\n                        SELECT survey_batch_id\n                        FROM survey_forms\n                        WHERE id = :survey_form_id\n                        LIMIT 1\n                        """\n                    ),\n                    {"survey_form_id": survey_form_id},\n                ).scalar()\n\n                if int(form_batch_id or 0) != int(batch_id):\n                    raise RuntimeError(\n                        f"Phiếu {survey_form_id} không thuộc đợt #{batch_id}."\n                    )\n\n                # Tổ 3 cấp là phân công chính thức mới của đúng phiếu này.\n                db.execute(\n                    text(\n                        """\n                        DELETE FROM survey_form_investigators\n                        WHERE survey_form_id = :survey_form_id\n                        """\n                    ),\n                    {"survey_form_id": survey_form_id},\n                )\n\n                for order_number, member in enumerate(members, start=1):\n                    db.execute(\n                        text(\n                            """\n                            INSERT INTO survey_form_investigators (\n                                survey_form_id,\n                                user_id,\n                                order_number,\n                                is_primary,\n                                signed_at,\n                                notes,\n                                created_at\n                            ) VALUES (\n                                :survey_form_id,\n                                :user_id,\n                                :order_number,\n                                :is_primary,\n                                :signed_at,\n                                :notes,\n                                :created_at\n                            )\n                            """\n                        ),\n                        {\n                            "survey_form_id": survey_form_id,\n                            "user_id": int(member["user_id"]),\n                            "order_number": order_number,\n                            "is_primary": 1 if order_number == 1 else 0,\n                            "signed_at": now_value,\n                            "notes": (\n                                f"Tổ điều tra 3 cấp số {team_number}; "\n                                f"cấp {member[\'level_code\']}; "\n                                f"xã/phường chốt ngày {now_value}."\n                            ),\n                            "created_at": now_value,\n                        },\n                    )\n\n                total_forms += 1\n                total_assignments += 3\n\n        # Sau ghi, mỗi phiếu trong dự thảo phải có đúng 3 người điều tra.\n        bad_form = db.execute(\n            text(\n                """\n                SELECT tf.survey_form_id\n                FROM survey_investigation_team_forms AS tf\n                JOIN survey_investigation_teams AS t\n                  ON t.id = tf.team_id\n                LEFT JOIN survey_form_investigators AS sfi\n                  ON sfi.survey_form_id = tf.survey_form_id\n                WHERE t.survey_batch_id = :batch_id\n                GROUP BY tf.survey_form_id\n                HAVING COUNT(sfi.id) != 3\n                LIMIT 1\n                """\n            ),\n            {"batch_id": int(batch_id)},\n        ).scalar()\n\n        if bad_form is not None:\n            raise RuntimeError(\n                f"Phiếu {bad_form} chưa có đúng 3 người điều tra sau chốt."\n            )\n\n        # Đánh dấu dự thảo đã chốt/gửi.\n        db.execute(\n            text(\n                """\n                UPDATE survey_investigation_teams\n                SET status = \'SENT\',\n                    updated_at = :updated_at\n                WHERE survey_batch_id = :batch_id\n                  AND status = \'DRAFT\'\n                """\n            ),\n            {\n                "batch_id": int(batch_id),\n                "updated_at": now_value,\n            },\n        )\n\n        generation_code = str(teams[0].get("generation_code") or "")\n\n        _generation_log(\n            db,\n            request=request,\n            batch_id=int(batch_id),\n            commune_id=int(batch["commune_id"]),\n            generation_code=generation_code,\n            action="FINALIZE_SEND",\n            team_count=len(teams),\n            household_count=total_forms,\n            mn_count=len(teams),\n            th_count=len(teams),\n            thcs_count=len(teams),\n            reserve_count=0,\n            notes=(\n                f"Đã chốt {total_forms} phiếu; "\n                f"ghi {total_assignments} lượt phân công "\n                "vào survey_form_investigators."\n            ),\n        )\n\n        db.commit()\n\n    except Exception:\n        db.rollback()\n        raise\n\n    return RedirectResponse(\n        url=(\n            "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n            f"?batch_id={batch_id}&status=sent"\n        ),\n        status_code=303,\n    )\n\n# BAI_13B_10_V3_1_FINALIZE_SEND_END\n'
BUTTON_BLOCK = '\n            <!-- === BAI_13B_10_V3_1_FINALIZE_BUTTON_START === -->\n            {% if preview.team_count > 0 and preview.teams and preview.teams[0].status == \'DRAFT\' %}\n            <form method="post" action="/dieu-tra/phan-cong-to-dieu-tra/lap-to/chot-gui">\n                <input type="hidden" name="batch_id" value="{{ batch.id }}">\n                <button\n                    class="button button-primary"\n                    type="submit"\n                    onclick="return confirm(\'CHỐT VÀ GỬI phân công này xuống các trường và giáo viên? Sau khi chốt sẽ không thể tạo lại ngẫu nhiên cho bản phân công này.\');"\n                >\n                    ✅ Chốt và gửi phân công\n                </button>\n            </form>\n            {% elif preview.team_count > 0 and preview.teams and preview.teams[0].status == \'SENT\' %}\n            <span class="ok" style="display:inline-block;margin:0">\n                ✅ Đã chốt và gửi xuống Trường/Giáo viên\n            </span>\n            {% endif %}\n            <!-- === BAI_13B_10_V3_1_FINALIZE_BUTTON_END === -->\n'


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


def patch_router_status_messages(text_value: str) -> str:
    # status_messages nằm trong ROUTER Python, KHÔNG nằm trong file HTML.
    # Đây chính là lỗi của bộ cài V3 trước.
    if '"sent": (' in text_value and '"already_sent": (' in text_value:
        return text_value

    anchor = "    status_messages = {\n"
    pos = text_value.find(anchor)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy status_messages trong survey_team_registration.py."
        )

    # Đảm bảo đây là status_messages của trang lập tổ:
    neighborhood = text_value[max(0, pos - 3000):pos + 3000]
    if "commune_team_builder_page" not in neighborhood:
        raise RuntimeError(
            "Tìm thấy status_messages nhưng không xác nhận được thuộc trang lập tổ."
        )

    insert_at = pos + len(anchor)
    block = (
        '        "sent": (\n'
        '            "Đã chốt và gửi phân công. Các trường và giáo viên trong tổ "\n'
        '            "đã có thể nhìn thấy đợt/phiếu được giao."\n'
        '        ),\n'
        '        "already_sent": (\n'
        '            "Phân công này đã được chốt và gửi trước đó; hệ thống không ghi lặp."\n'
        '        ),\n'
        '        "no_draft": (\n'
        '            "Chưa có dự thảo tổ để chốt và gửi."\n'
        '        ),\n'
    )
    return text_value[:insert_at] + block + text_value[insert_at:]


def patch_router(text_value: str) -> str:
    text_value = patch_router_status_messages(text_value)

    if ROUTE_MARK in text_value:
        return text_value

    required = [
        "BAI_13B_10_V2_RANDOM_TEAMS_START",
        '@router.get("/lap-to"',
        "survey_investigation_teams",
        "survey_investigation_team_members",
        "survey_investigation_team_forms",
        "survey_form_investigators",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(
                f"Router chưa có nền cần thiết: {marker}"
            )

    # Chèn trước route xóa dự thảo: route POST mới ở đúng nhóm /lap-to.
    anchor = '@router.post("/lap-to/xoa-du-thao")'
    pos = text_value.find(anchor)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy route /lap-to/xoa-du-thao để chèn V3.1."
        )

    return (
        text_value[:pos]
        + ROUTE_BLOCK.strip()
        + "\n\n\n"
        + text_value[pos:]
    )


def patch_builder(text_value: str) -> str:
    if BUTTON_MARK in text_value:
        return text_value

    # Bộ cài cũ sai ở đây vì đi tìm status_messages trong HTML.
    # V3.1 chỉ chèn nút vào vùng actions của HTML.
    anchor = '<div class="actions" style="margin-top:16px">'
    pos = text_value.find(anchor)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy vùng actions trong commune_team_builder.html."
        )

    insert_at = pos + len(anchor)
    return (
        text_value[:insert_at]
        + "\n"
        + BUTTON_BLOCK.strip()
        + "\n"
        + text_value[insert_at:]
    )


def verify() -> None:
    router_text = read_text(ROUTER)
    builder_text = read_text(BUILDER)

    for marker in (
        ROUTE_MARK,
        '@router.post("/lap-to/chot-gui")',
        "INSERT INTO survey_form_investigators",
        "SET status = 'SENT'",
        "FINALIZE_SEND",
        '"sent": (',
        '"already_sent": (',
    ):
        if marker not in router_text:
            raise RuntimeError(
                f"Kiểm tra router chưa đạt: {marker}"
            )

    for marker in (
        BUTTON_MARK,
        "✅ Chốt và gửi phân công",
        "/lap-to/chot-gui",
        "preview.teams[0].status == 'DRAFT'",
    ):
        if marker not in builder_text:
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
    env.get_template("survey_teams/commune_team_builder.html")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 112)
    print("BÀI 13B-10 V3.1 - SỬA BỘ CÀI CHỐT/GỬI PHÂN CÔNG")
    print("=" * 112)
    print("")
    print("NGUYÊN NHÂN V3 TRƯỚC BỊ LỖI:")
    print(" - Bộ cài đã tìm biến Python 'status_messages' trong file HTML.")
    print(" - Thực tế status_messages nằm trong survey_team_registration.py.")
    print(" - Vì vậy V3 đã rollback an toàn và chưa thay đổi source.")
    print("")
    print("V3.1:")
    print(" - Chèn status_messages đúng trong ROUTER Python.")
    print(" - Chèn nút 'Chốt và gửi phân công' đúng trong template HTML.")
    print(" - Chốt mỗi phiếu cho đúng 3 GV MN + TH + THCS.")
    print(" - Ghi chính thức vào survey_form_investigators.")
    print(" - Đánh dấu tổ SENT sau khi commit thành công.")
    print("")
    print("KHÔNG thay đổi hộ dân, thành viên hộ hoặc dữ liệu Đội ngũ.")
    print("")

    for path in (ROUTER, BUILDER):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER)
    backup_file(BUILDER)

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
        BUILDER.write_text(
            patch_builder(read_text(BUILDER)),
            encoding="utf-8",
        )

        verify()
        clear_cache()

        print("")
        print("CAI DAT BAI 13B-10 V3.1 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("SAU KHI KHỞI ĐỘNG LẠI:")
        print(" 1. Đăng nhập Xã -> Lập tổ điều tra 3 cấp.")
        print(" 2. Giữ nguyên 5 tổ hiện tại; KHÔNG cần tạo lại.")
        print(" 3. Phải thấy nút '✅ Chốt và gửi phân công'.")
        print(" 4. Bấm nút và xác nhận.")
        print(" 5. Đăng nhập Trường THCS Hải Hòa -> /dieu-tra.")
        print(" 6. Trường phải thấy đợt 2026-2027 và các phiếu được giao.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore_file(ROUTER)
        restore_file(BUILDER)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE TRƯỚC V3.1.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
