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
ROUTER = APP / "routers" / "survey_team_registration.py"
BUILDER = APP / "templates" / "survey_teams" / "commune_team_builder.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v3_2_{STAMP}"

ROUTE_MARK = "BAI_13B_10_V3_2_FINALIZE_SEND_START"
BUTTON_MARK = "BAI_13B_10_V3_2_FINALIZE_BUTTON_START"

ROUTE_BLOCK = '# =========================================================\n# BAI_13B_10_V3_2_FINALIZE_SEND_START\n# Chốt tổ 3 cấp và ghi chính thức vào survey_form_investigators.\n# =========================================================\n\n@router.post("/lap-to/chot-gui")\nasync def finalize_and_send_team_assignments_v3_2(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n\n    _ensure_schema(db)\n    _ensure_team_schema(db)\n\n    form = await request.form()\n    try:\n        batch_id = int(form.get("batch_id") or 0)\n    except (TypeError, ValueError):\n        batch_id = 0\n\n    batch = _commune_batch_scope(db, request, batch_id)\n    if batch is None:\n        return _forbidden()\n\n    teams = [\n        dict(row)\n        for row in db.execute(\n            text(\n                """\n                SELECT id, team_number, status, generation_code\n                FROM survey_investigation_teams\n                WHERE survey_batch_id = :batch_id\n                ORDER BY team_number\n                """\n            ),\n            {"batch_id": int(batch_id)},\n        ).mappings().all()\n    ]\n\n    if not teams:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n                f"?batch_id={batch_id}&status=no_draft"\n            ),\n            status_code=303,\n        )\n\n    if any(str(row.get("status") or "") != "DRAFT" for row in teams):\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n                f"?batch_id={batch_id}&status=already_sent"\n            ),\n            status_code=303,\n        )\n\n    now_value = datetime.now().isoformat(\n        sep=" ",\n        timespec="seconds",\n    )\n    total_forms = 0\n\n    try:\n        for team in teams:\n            team_id = int(team["id"])\n            team_number = int(team["team_number"])\n\n            members = [\n                dict(row)\n                for row in db.execute(\n                    text(\n                        """\n                        SELECT\n                            tm.user_id,\n                            tm.level_code,\n                            tm.order_number,\n                            u.is_active\n                        FROM survey_investigation_team_members tm\n                        JOIN users u ON u.id = tm.user_id\n                        WHERE tm.team_id = :team_id\n                        ORDER BY tm.order_number\n                        """\n                    ),\n                    {"team_id": team_id},\n                ).mappings().all()\n            ]\n\n            levels = {\n                str(item.get("level_code") or "")\n                for item in members\n            }\n            if (\n                len(members) != 3\n                or levels != {"MN", "TH", "THCS"}\n                or any(int(item.get("is_active") or 0) != 1 for item in members)\n            ):\n                raise RuntimeError(\n                    f"Tổ {team_number} không đủ đúng 3 giáo viên "\n                    "MN + TH + THCS đang hoạt động."\n                )\n\n            form_ids = [\n                int(value)\n                for value in db.execute(\n                    text(\n                        """\n                        SELECT survey_form_id\n                        FROM survey_investigation_team_forms\n                        WHERE team_id = :team_id\n                        ORDER BY assignment_order\n                        """\n                    ),\n                    {"team_id": team_id},\n                ).scalars().all()\n            ]\n\n            if not form_ids:\n                raise RuntimeError(\n                    f"Tổ {team_number} không có hộ/phiếu."\n                )\n\n            for survey_form_id in form_ids:\n                correct_batch = db.execute(\n                    text(\n                        """\n                        SELECT 1\n                        FROM survey_forms\n                        WHERE id = :survey_form_id\n                          AND survey_batch_id = :batch_id\n                        LIMIT 1\n                        """\n                    ),\n                    {\n                        "survey_form_id": survey_form_id,\n                        "batch_id": int(batch_id),\n                    },\n                ).scalar()\n\n                if correct_batch is None:\n                    raise RuntimeError(\n                        f"Phiếu {survey_form_id} không thuộc đợt #{batch_id}."\n                    )\n\n                db.execute(\n                    text(\n                        """\n                        DELETE FROM survey_form_investigators\n                        WHERE survey_form_id = :survey_form_id\n                        """\n                    ),\n                    {"survey_form_id": survey_form_id},\n                )\n\n                for order_number, member in enumerate(members, start=1):\n                    db.execute(\n                        text(\n                            """\n                            INSERT INTO survey_form_investigators (\n                                survey_form_id,\n                                user_id,\n                                order_number,\n                                is_primary,\n                                signed_at,\n                                notes,\n                                created_at\n                            ) VALUES (\n                                :survey_form_id,\n                                :user_id,\n                                :order_number,\n                                :is_primary,\n                                :signed_at,\n                                :notes,\n                                :created_at\n                            )\n                            """\n                        ),\n                        {\n                            "survey_form_id": survey_form_id,\n                            "user_id": int(member["user_id"]),\n                            "order_number": order_number,\n                            "is_primary": 1 if order_number == 1 else 0,\n                            "signed_at": now_value,\n                            "notes": (\n                                f"Tổ điều tra 3 cấp số {team_number}; "\n                                f"{member[\'level_code\']}; chốt {now_value}"\n                            ),\n                            "created_at": now_value,\n                        },\n                    )\n\n                total_forms += 1\n\n        bad_form = db.execute(\n            text(\n                """\n                SELECT tf.survey_form_id\n                FROM survey_investigation_team_forms tf\n                JOIN survey_investigation_teams t\n                  ON t.id = tf.team_id\n                LEFT JOIN survey_form_investigators sfi\n                  ON sfi.survey_form_id = tf.survey_form_id\n                WHERE t.survey_batch_id = :batch_id\n                GROUP BY tf.survey_form_id\n                HAVING COUNT(sfi.id) != 3\n                LIMIT 1\n                """\n            ),\n            {"batch_id": int(batch_id)},\n        ).scalar()\n\n        if bad_form is not None:\n            raise RuntimeError(\n                f"Phiếu {bad_form} chưa có đúng 3 người điều tra."\n            )\n\n        db.execute(\n            text(\n                """\n                UPDATE survey_investigation_teams\n                SET status = \'SENT\',\n                    updated_at = :updated_at\n                WHERE survey_batch_id = :batch_id\n                  AND status = \'DRAFT\'\n                """\n            ),\n            {\n                "batch_id": int(batch_id),\n                "updated_at": now_value,\n            },\n        )\n\n        _generation_log(\n            db,\n            request=request,\n            batch_id=int(batch_id),\n            commune_id=int(batch["commune_id"]),\n            generation_code=str(\n                teams[0].get("generation_code") or ""\n            ),\n            action="FINALIZE_SEND",\n            team_count=len(teams),\n            household_count=total_forms,\n            mn_count=len(teams),\n            th_count=len(teams),\n            thcs_count=len(teams),\n            reserve_count=0,\n            notes=(\n                f"Chốt và gửi {total_forms} phiếu; "\n                f"{total_forms * 3} lượt phân công."\n            ),\n        )\n\n        db.commit()\n\n    except Exception:\n        db.rollback()\n        raise\n\n    return RedirectResponse(\n        url=(\n            "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n            f"?batch_id={batch_id}&status=sent"\n        ),\n        status_code=303,\n    )\n\n# BAI_13B_10_V3_2_FINALIZE_SEND_END'
BUTTON_BLOCK = '<!-- === BAI_13B_10_V3_2_FINALIZE_BUTTON_START === -->\n            {% if preview.team_count > 0 and preview.team_status == \'DRAFT\' %}\n            <form\n                method="post"\n                action="/dieu-tra/phan-cong-to-dieu-tra/lap-to/chot-gui"\n                style="display:inline-block"\n            >\n                <input type="hidden" name="batch_id" value="{{ batch.id }}">\n                <button\n                    class="button button-primary"\n                    type="submit"\n                    onclick="return confirm(\'Chốt và gửi phân công 3 cấp xuống Trường/Giáo viên? Sau khi chốt sẽ không thể tạo lại ngẫu nhiên bản phân công này.\');"\n                >\n                    ✅ Chốt và gửi phân công\n                </button>\n            </form>\n            {% elif preview.team_count > 0 and preview.team_status == \'SENT\' %}\n            <span class="ok" style="display:inline-block;margin:0">\n                ✅ Đã chốt và gửi xuống Trường/Giáo viên\n            </span>\n            {% endif %}\n            <!-- === BAI_13B_10_V3_2_FINALIZE_BUTTON_END === -->'


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


def patch_preview_status(text_value: str) -> str:
    # _team_preview_data đã đọc t.status từ DB nhưng chưa đưa một status
    # riêng ra ngoài preview để template dùng ổn định.
    if '"team_status":' in text_value:
        return text_value

    function_pos = text_value.find("def _team_preview_data(")
    if function_pos < 0:
        raise RuntimeError("Không tìm thấy def _team_preview_data().")

    next_route = text_value.find('@router.get("/lap-to"', function_pos)
    if next_route < 0:
        raise RuntimeError("Không xác định được cuối _team_preview_data().")

    block = text_value[function_pos:next_route]
    anchor = '        "teams": teams,\n'
    if anchor not in block:
        raise RuntimeError(
            "Không tìm thấy key teams trong return của _team_preview_data()."
        )

    block = block.replace(
        anchor,
        anchor
        + '        "team_status": str(teams[0].get("status") or "") if teams else "",\n',
        1,
    )
    return text_value[:function_pos] + block + text_value[next_route:]


def patch_status_messages(text_value: str) -> str:
    # Chỉ sửa status_messages trong ROUTER.
    route_pos = text_value.find(
        '@router.get("/lap-to", response_class=HTMLResponse)'
    )
    if route_pos < 0:
        raise RuntimeError("Không tìm thấy route GET /lap-to.")

    next_route = text_value.find("@router.", route_pos + 10)
    if next_route < 0:
        next_route = len(text_value)

    block = text_value[route_pos:next_route]

    if '"sent": (' not in block:
        anchor = "    status_messages = {\n"
        if anchor not in block:
            raise RuntimeError(
                "Không tìm thấy status_messages trong route GET /lap-to."
            )

        add = (
            '        "sent": (\n'
            '            "Đã chốt và gửi phân công xuống Trường/Giáo viên."\n'
            '        ),\n'
            '        "already_sent": (\n'
            '            "Phân công này đã được chốt trước đó; không ghi lặp."\n'
            '        ),\n'
            '        "no_draft": (\n'
            '            "Chưa có dự thảo tổ để chốt và gửi."\n'
            '        ),\n'
        )
        block = block.replace(anchor, anchor + add, 1)

    return text_value[:route_pos] + block + text_value[next_route:]


def patch_finalize_route(text_value: str) -> str:
    # Nếu V3.1 đã cài route thì giữ nguyên route đó.
    if '@router.post("/lap-to/chot-gui")' in text_value:
        return text_value

    anchor = '@router.post("/lap-to/xoa-du-thao")'
    pos = text_value.find(anchor)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy route /lap-to/xoa-du-thao."
        )

    return (
        text_value[:pos]
        + ROUTE_BLOCK
        + "\n\n\n"
        + text_value[pos:]
    )


def remove_old_v3_button(text_value: str) -> str:
    patterns = [
        (
            r'\s*<!-- === BAI_13B_10_V3_1_FINALIZE_BUTTON_START === -->'
            r'.*?'
            r'<!-- === BAI_13B_10_V3_1_FINALIZE_BUTTON_END === -->\s*'
        ),
        (
            r'\s*<!-- === BAI_13B_10_V3_FINALIZE_BUTTON_START === -->'
            r'.*?'
            r'<!-- === BAI_13B_10_V3_FINALIZE_BUTTON_END === -->\s*'
        ),
    ]
    for pattern in patterns:
        text_value = re.sub(
            pattern,
            "\n",
            text_value,
            count=1,
            flags=re.S,
        )
    return text_value


def patch_builder(text_value: str) -> str:
    text_value = remove_old_v3_button(text_value)

    if BUTTON_MARK in text_value:
        return text_value

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
        + BUTTON_BLOCK
        + "\n"
        + text_value[insert_at:]
    )


def verify() -> None:
    router_text = read_text(ROUTER)
    builder_text = read_text(BUILDER)

    required_router = [
        '"team_status": str(teams[0].get("status") or "") if teams else ""',
        '@router.post("/lap-to/chot-gui")',
        '"sent": (',
        '"already_sent": (',
    ]
    for marker in required_router:
        if marker not in router_text:
            raise RuntimeError(
                f"Kiểm tra router chưa đạt: {marker}"
            )

    required_builder = [
        BUTTON_MARK,
        "preview.team_status == 'DRAFT'",
        "✅ Chốt và gửi phân công",
        "/lap-to/chot-gui",
    ]
    for marker in required_builder:
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
    print("BÀI 13B-10 V3.2 - SỬA HIỂN THỊ NÚT CHỐT VÀ GỬI")
    print("=" * 112)
    print("")
    print("ĐÃ XÁC ĐỊNH:")
    print(" - 5 tổ hiện tại đã đúng, mỗi tổ 1 hộ.")
    print(" - _team_preview_data() đã đọc t.status từ database.")
    print(" - V3.1 dùng điều kiện template chưa đủ ổn định.")
    print("")
    print("V3.2:")
    print(" - Đưa team_status ra trực tiếp trong preview.")
    print(" - DRAFT -> hiện nút 'Chốt và gửi phân công'.")
    print(" - SENT  -> hiện nhãn 'Đã chốt và gửi'.")
    print(" - Nếu route chốt/gửi của V3.1 đã có thì giữ nguyên.")
    print(" - Nếu chưa có thì bổ sung route chốt/gửi.")
    print("")
    print("KHÔNG thay đổi database trong lúc cài.")
    print("KHÔNG tạo lại 5 tổ hiện tại.")
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
        router_text = read_text(ROUTER)
        router_text = patch_preview_status(router_text)
        router_text = patch_status_messages(router_text)
        router_text = patch_finalize_route(router_text)

        ROUTER.write_text(router_text, encoding="utf-8")
        BUILDER.write_text(
            patch_builder(read_text(BUILDER)),
            encoding="utf-8",
        )

        verify()
        clear_cache()

        print("")
        print("CAI DAT BAI 13B-10 V3.2 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("SAU CÀI:")
        print(" 1. Khởi động lại Uvicorn.")
        print(" 2. Ctrl+F5.")
        print(" 3. Giữ nguyên 5 tổ hiện tại.")
        print(" 4. Phải thấy nút: ✅ Chốt và gửi phân công")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore_file(ROUTER)
        restore_file(BUILDER)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE TRƯỚC V3.2.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
