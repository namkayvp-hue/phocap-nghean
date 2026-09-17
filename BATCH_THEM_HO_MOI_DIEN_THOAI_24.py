# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import py_compile
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
SURVEYS = APP / "routers" / "surveys.py"
HOUSEHOLDS = APP / "templates" / "surveys" / "households.html"

BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_THEM_HO_MOI_DIEN_THOAI_24.txt"

ROUTE_MARK = "BATCH24_MOBILE_ADD_HOUSEHOLD_START"
UI_MARK = "BATCH24_MOBILE_ADD_HOUSEHOLD_UI_START"
CSS_MARK = "BATCH24_MOBILE_ADD_HOUSEHOLD_CSS_START"

ROUTE_BLOCK = '\n# === BATCH24_MOBILE_ADD_HOUSEHOLD_START ===\n@router.post("/{batch_id}/ho-dan/them-mobile")\ndef them_ho_dan_tu_dien_thoai(\n    batch_id: int,\n    request: Request,\n    head_name: Annotated[str, Form()],\n    address: Annotated[str, Form()],\n    hamlet_name: Annotated[str, Form()] = "",\n    phone: Annotated[str, Form()] = "",\n    notes: Annotated[str, Form()] = "",\n    db: Session = Depends(get_db),\n):\n    """\n    Giáo viên thêm hộ phát sinh ngay tại thực địa trên điện thoại.\n\n    Quy tắc:\n    - Chỉ tài khoản GIAO_VIEN.\n    - Giáo viên phải thuộc đúng 1 tổ điều tra của đợt.\n    - Hộ/phiếu mới được tự gắn vào chính tổ 3 cấp đó.\n    - Cả 3 thành viên MN + TH + THCS đều nhận phiếu mới.\n    - Không đụng dữ liệu trường/lớp/GV/HS đối chiếu.\n    """\n    batch = lay_dot_dieu_tra(db, batch_id)\n    if batch is None:\n        return RedirectResponse(url="/dieu-tra", status_code=303)\n\n    base_url = f"/dieu-tra/{batch.id}/ho-dan?page_size=100&sort=hamlet"\n\n    def _mobile_error(message: str) -> RedirectResponse:\n        return RedirectResponse(\n            url=base_url + "&" + urlencode({\n                "mobile_add": "1",\n                "mobile_add_error": message,\n            }),\n            status_code=303,\n        )\n\n    user = lay_thong_tin_nguoi_dung(request)\n    role_code = normalize_role_code(user.get("role_code"))\n    user_id = user.get("id")\n\n    if role_code != TEACHER_ROLE_CODE or user_id is None:\n        return _mobile_error(\n            "Chỉ giáo viên được phép thêm hộ phát sinh trên giao diện điện thoại."\n        )\n\n    if batch.status == "DA_KET_THUC":\n        return _mobile_error(\n            "Đợt điều tra đã kết thúc, không thể thêm hộ mới."\n        )\n\n    head_name = chuan_hoa_van_ban(head_name)\n    address = chuan_hoa_van_ban(address)\n    hamlet_name = chuan_hoa_van_ban(hamlet_name)\n    phone_value = chuan_hoa_so_dien_thoai(phone)\n    notes = notes.strip()\n\n    errors: list[str] = []\n    if not head_name:\n        errors.append("Họ và tên chủ hộ không được để trống.")\n    if len(head_name) > 200:\n        errors.append("Họ và tên chủ hộ dài quá 200 ký tự.")\n    if not address:\n        errors.append("Địa chỉ hộ gia đình không được để trống.")\n    if len(hamlet_name) > 200:\n        errors.append("Tên thôn/xóm dài quá 200 ký tự.")\n    if phone_value and len(phone_value) > 30:\n        errors.append("Số điện thoại dài quá 30 ký tự.")\n\n    if errors:\n        return _mobile_error(" ".join(errors))\n\n    try:\n        # Xác định đúng tổ hiện hành của giáo viên trong đợt.\n        team_rows = db.execute(\n            text(\n                """\n                SELECT DISTINCT\n                    t.id AS team_id,\n                    t.team_number,\n                    t.status\n                FROM survey_investigation_teams AS t\n                JOIN survey_investigation_team_members AS tm\n                  ON tm.team_id = t.id\n                JOIN survey_investigation_team_forms AS tf\n                  ON tf.team_id = t.id\n                JOIN survey_form_investigators AS sfi\n                  ON sfi.survey_form_id = tf.survey_form_id\n                 AND sfi.user_id = tm.user_id\n                WHERE t.survey_batch_id = :batch_id\n                  AND tm.user_id = :user_id\n                ORDER BY t.id DESC\n                """\n            ),\n            {\n                "batch_id": int(batch.id),\n                "user_id": int(user_id),\n            },\n        ).mappings().all()\n    except Exception:\n        db.rollback()\n        return _mobile_error(\n            "Chưa xác định được tổ điều tra của giáo viên. "\n            "Hãy báo xã/phường kiểm tra phân công tổ 3 cấp."\n        )\n\n    if len(team_rows) == 0:\n        return _mobile_error(\n            "Giáo viên chưa thuộc tổ điều tra đã được giao phiếu trong đợt này."\n        )\n    if len(team_rows) > 1:\n        return _mobile_error(\n            "Tài khoản đang thuộc nhiều tổ điều tra trong cùng đợt. "\n            "Hãy báo xã/phường kiểm tra trước khi thêm hộ."\n        )\n\n    team_id = int(team_rows[0]["team_id"])\n    team_number = int(team_rows[0]["team_number"] or 0)\n\n    members = db.execute(\n        text(\n            """\n            SELECT\n                tm.user_id,\n                tm.school_id,\n                tm.level_code,\n                tm.order_number,\n                u.is_active\n            FROM survey_investigation_team_members AS tm\n            JOIN users AS u ON u.id = tm.user_id\n            WHERE tm.team_id = :team_id\n            ORDER BY tm.order_number, tm.id\n            """\n        ),\n        {"team_id": team_id},\n    ).mappings().all()\n\n    member_levels = {\n        str(row["level_code"] or "").strip().upper()\n        for row in members\n    }\n\n    if (\n        len(members) != 3\n        or member_levels != {"MN", "TH", "THCS"}\n        or any(int(row["is_active"] or 0) != 1 for row in members)\n    ):\n        return _mobile_error(\n            "Tổ điều tra hiện tại chưa đủ đúng 3 giáo viên hoạt động "\n            "MN + TH + THCS. Không tạo hộ để tránh sai phân công."\n        )\n\n    existing_household = db.scalar(\n        select(Household).where(\n            Household.commune_id == batch.commune_id,\n            Household.head_name == head_name,\n            Household.address == address,\n        )\n    )\n\n    if existing_household is not None:\n        existing_form = db.scalar(\n            select(SurveyForm).where(\n                SurveyForm.survey_batch_id == batch.id,\n                SurveyForm.household_id == existing_household.id,\n            )\n        )\n        if existing_form is not None:\n            return _mobile_error(\n                "Hộ này đã có phiếu trong đợt điều tra hiện tại. "\n                "Hãy dùng tìm kiếm để mở hộ đã có."\n            )\n\n    now_value = datetime.now().isoformat(sep=" ", timespec="seconds")\n\n    try:\n        if existing_household is None:\n            household = Household(\n                code=tao_ma_ho(\n                    db=db,\n                    commune=batch.commune,\n                ),\n                commune_id=batch.commune_id,\n                head_name=head_name,\n                hamlet_name=hamlet_name or None,\n                address=address,\n                phone=phone_value,\n                notes=notes or None,\n                is_active=True,\n            )\n            db.add(household)\n            db.flush()\n        else:\n            household = existing_household\n            if hamlet_name:\n                household.hamlet_name = hamlet_name\n            if phone_value:\n                household.phone = phone_value\n            if notes:\n                household.notes = notes\n            household.is_active = True\n\n        survey_form = SurveyForm(\n            survey_batch_id=batch.id,\n            household_id=household.id,\n            form_number=tao_so_phieu(\n                db=db,\n                batch=batch,\n            ),\n            head_name_snapshot=household.head_name,\n            address_snapshot=household.address,\n            hamlet_name_snapshot=household.hamlet_name,\n            survey_date=None,\n            status="CHUA_DIEU_TRA",\n            village_head_name=None,\n            household_representative_name=None,\n            household_confirmed_at=None,\n            commune_confirmed_at=None,\n            notes=(\n                "Hộ phát sinh tại thực địa, do giáo viên thêm trên điện thoại. "\n                f"Tổ điều tra 3 cấp số {team_number}."\n            ),\n        )\n        db.add(survey_form)\n        db.flush()\n\n        next_assignment_order = int(\n            db.execute(\n                text(\n                    """\n                    SELECT COALESCE(MAX(assignment_order), 0) + 1\n                    FROM survey_investigation_team_forms\n                    WHERE team_id = :team_id\n                    """\n                ),\n                {"team_id": team_id},\n            ).scalar()\n            or 1\n        )\n\n        db.execute(\n            text(\n                """\n                INSERT INTO survey_investigation_team_forms (\n                    team_id,\n                    survey_form_id,\n                    assignment_order,\n                    created_at\n                ) VALUES (\n                    :team_id,\n                    :survey_form_id,\n                    :assignment_order,\n                    :created_at\n                )\n                """\n            ),\n            {\n                "team_id": team_id,\n                "survey_form_id": int(survey_form.id),\n                "assignment_order": next_assignment_order,\n                "created_at": now_value,\n            },\n        )\n\n        for member in members:\n            order_number = int(member["order_number"] or 0)\n            db.execute(\n                text(\n                    """\n                    INSERT INTO survey_form_investigators (\n                        survey_form_id,\n                        user_id,\n                        order_number,\n                        is_primary,\n                        signed_at,\n                        notes,\n                        created_at\n                    ) VALUES (\n                        :survey_form_id,\n                        :user_id,\n                        :order_number,\n                        :is_primary,\n                        :signed_at,\n                        :notes,\n                        :created_at\n                    )\n                    """\n                ),\n                {\n                    "survey_form_id": int(survey_form.id),\n                    "user_id": int(member["user_id"]),\n                    "order_number": order_number,\n                    "is_primary": 1 if order_number == 1 else 0,\n                    "signed_at": now_value,\n                    "notes": (\n                        "Hộ phát sinh trên điện thoại; "\n                        f"Tổ điều tra 3 cấp số {team_number}; "\n                        f"cấp {str(member[\'level_code\'] or \'\')}."\n                    ),\n                    "created_at": now_value,\n                },\n            )\n\n        assigned_count = int(\n            db.execute(\n                text(\n                    """\n                    SELECT COUNT(*)\n                    FROM survey_form_investigators\n                    WHERE survey_form_id = :survey_form_id\n                    """\n                ),\n                {"survey_form_id": int(survey_form.id)},\n            ).scalar()\n            or 0\n        )\n\n        team_form_count = int(\n            db.execute(\n                text(\n                    """\n                    SELECT COUNT(*)\n                    FROM survey_investigation_team_forms\n                    WHERE team_id = :team_id\n                      AND survey_form_id = :survey_form_id\n                    """\n                ),\n                {\n                    "team_id": team_id,\n                    "survey_form_id": int(survey_form.id),\n                },\n            ).scalar()\n            or 0\n        )\n\n        if assigned_count != 3 or team_form_count != 1:\n            raise RuntimeError(\n                "Post-check phân công hộ phát sinh không đạt."\n            )\n\n        db.commit()\n\n    except IntegrityError:\n        db.rollback()\n        return _mobile_error(\n            "Không thể tạo hộ vì dữ liệu bị trùng hoặc vi phạm ràng buộc. "\n            "Dữ liệu chưa được thay đổi."\n        )\n    except Exception:\n        db.rollback()\n        return _mobile_error(\n            "Không thể tạo hộ phát sinh. Dữ liệu đã rollback, chưa thay đổi."\n        )\n\n    return RedirectResponse(\n        url=(\n            f"/dieu-tra/{batch.id}/ho-dan/{household.id}/nhap-nhanh"\n            + "?"\n            + urlencode({"status": "household_created"})\n        ),\n        status_code=303,\n    )\n# === BATCH24_MOBILE_ADD_HOUSEHOLD_END ===\n'
CSS_BLOCK = '\n        /* === BATCH24_MOBILE_ADD_HOUSEHOLD_CSS_START === */\n        .pc-gv-v24-add-household {\n            display: none;\n        }\n\n        @media (max-width: 760px) {\n            .pc-gv-v24-add-household {\n                display: block;\n                margin: 0 0 14px;\n                border: 1px solid #b8d5ee;\n                border-radius: 14px;\n                background: #f6fbff;\n                overflow: hidden;\n            }\n\n            .pc-gv-v24-add-household > summary {\n                list-style: none;\n                cursor: pointer;\n                min-height: 52px;\n                padding: 14px 15px;\n                background: #15803d;\n                color: #fff;\n                font-size: 17px;\n                font-weight: 900;\n                display: flex;\n                align-items: center;\n                justify-content: center;\n                text-align: center;\n            }\n\n            .pc-gv-v24-add-household > summary::-webkit-details-marker {\n                display: none;\n            }\n\n            .pc-gv-v24-add-household[open] > summary {\n                background: #166534;\n            }\n\n            .pc-gv-v24-add-body {\n                padding: 13px;\n            }\n\n            .pc-gv-v24-add-note {\n                margin: 0 0 11px;\n                padding: 10px;\n                border-radius: 10px;\n                background: #e8f4ff;\n                color: #24445e;\n                font-size: 13px;\n                line-height: 1.45;\n            }\n\n            .pc-gv-v24-add-grid {\n                display: grid;\n                grid-template-columns: 1fr;\n                gap: 10px;\n            }\n\n            .pc-gv-v24-add-grid label {\n                display: block;\n                margin-bottom: 5px;\n                color: #23394d;\n                font-size: 13px;\n                font-weight: 800;\n            }\n\n            .pc-gv-v24-add-grid input,\n            .pc-gv-v24-add-grid textarea {\n                width: 100%;\n                box-sizing: border-box;\n                min-height: 48px;\n                padding: 10px 11px;\n                border: 1px solid #aebfce;\n                border-radius: 10px;\n                background: #fff;\n                color: #142536;\n                font-size: 16px;\n            }\n\n            .pc-gv-v24-add-grid textarea {\n                min-height: 74px;\n                resize: vertical;\n            }\n\n            .pc-gv-v24-add-submit {\n                width: 100%;\n                min-height: 52px;\n                margin-top: 12px;\n                border: 0;\n                border-radius: 11px;\n                background: #0f5fa8;\n                color: #fff;\n                font-size: 16px;\n                font-weight: 900;\n                cursor: pointer;\n            }\n\n            .pc-gv-v24-add-error {\n                margin: 0 0 12px;\n                padding: 10px 12px;\n                border-radius: 10px;\n                background: #fee2e2;\n                color: #991b1b;\n                font-size: 13px;\n                font-weight: 700;\n                line-height: 1.45;\n            }\n        }\n        /* === BATCH24_MOBILE_ADD_HOUSEHOLD_CSS_END === */\n'
HTML_BLOCK = '\n        <!-- === BATCH24_MOBILE_ADD_HOUSEHOLD_UI_START === -->\n        {% if\n            nguoi_dung.role_code == \'GIAO_VIEN\'\n            and co_quyen_cap_nhat_du_lieu\n            and batch.status != \'DA_KET_THUC\'\n        %}\n            {% if request.query_params.get(\'mobile_add_error\') %}\n            <div class="pc-gv-v24-add-error">\n                {{ request.query_params.get(\'mobile_add_error\') }}\n            </div>\n            {% endif %}\n\n            <details\n                class="pc-gv-v24-add-household"\n                {% if request.query_params.get(\'mobile_add\') == \'1\' %}open{% endif %}\n            >\n                <summary>＋ THÊM HỘ MỚI</summary>\n\n                <div class="pc-gv-v24-add-body">\n                    <p class="pc-gv-v24-add-note">\n                        Dùng khi phát hiện hộ mới tại thực địa.\n                        Hộ được tạo sẽ tự gắn vào đúng tổ điều tra 3 cấp\n                        của giáo viên và mở thẳng màn hình Nhập nhanh.\n                    </p>\n\n                    <form\n                        method="post"\n                        action="/dieu-tra/{{ batch.id }}/ho-dan/them-mobile"\n                    >\n                        <div class="pc-gv-v24-add-grid">\n                            <div>\n                                <label>Họ và tên chủ hộ *</label>\n                                <input\n                                    name="head_name"\n                                    autocomplete="name"\n                                    required\n                                >\n                            </div>\n\n                            <div>\n                                <label>Thôn/xóm</label>\n                                <input\n                                    name="hamlet_name"\n                                    autocomplete="address-level3"\n                                >\n                            </div>\n\n                            <div>\n                                <label>Địa chỉ *</label>\n                                <input\n                                    name="address"\n                                    autocomplete="street-address"\n                                    required\n                                >\n                            </div>\n\n                            <div>\n                                <label>Số điện thoại</label>\n                                <input\n                                    name="phone"\n                                    type="tel"\n                                    inputmode="tel"\n                                    autocomplete="tel"\n                                >\n                            </div>\n\n                            <div>\n                                <label>Ghi chú</label>\n                                <textarea\n                                    name="notes"\n                                    placeholder="Ví dụ: Hộ phát sinh mới tại thực địa"\n                                ></textarea>\n                            </div>\n                        </div>\n\n                        <button\n                            class="pc-gv-v24-add-submit"\n                            type="submit"\n                        >\n                            TẠO HỘ VÀ NHẬP NHANH\n                        </button>\n                    </form>\n                </div>\n            </details>\n        {% endif %}\n        <!-- === BATCH24_MOBILE_ADD_HOUSEHOLD_UI_END === -->\n'


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def log(f, *parts):
    s = " ".join(str(x) for x in parts)
    print(s)
    f.write(s + "\n")
    f.flush()


def db_health():
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        tables = {
            str(r[0])
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        con.close()

    required = {
        "households",
        "survey_forms",
        "survey_form_investigators",
        "survey_investigation_teams",
        "survey_investigation_team_members",
        "survey_investigation_team_forms",
    }
    missing = sorted(required - tables)
    if missing:
        raise RuntimeError(
            "Thiếu bảng cần cho luồng tổ điều tra 3 cấp: " + repr(missing)
        )

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}, fk={len(fk)}"
        )

    return integrity, len(fk)


def backup_file(path: Path, root: Path):
    dst = root / path.relative_to(ROOT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)
    return dst


def restore_file(target: Path, backup: Path):
    shutil.copy2(backup, target)


def patch_surveys(text: str):
    if ROUTE_MARK in text:
        return text, "ALREADY_PRESENT"

    anchor = '@router.post("/{batch_id}/ho-dan/them")'
    count = text.count(anchor)
    if count != 1:
        raise RuntimeError(
            f"Không tìm đúng route thêm hộ hiện có; count={count}."
        )

    return (
        text.replace(
            anchor,
            ROUTE_BLOCK.rstrip() + "\n\n\n" + anchor,
            1,
        ),
        "ADDED"
    )


def patch_households(text: str):
    statuses = []

    if CSS_MARK not in text:
        if "</style>" not in text:
            raise RuntimeError("households.html không có </style>.")
        text = text.replace(
            "</style>",
            CSS_BLOCK.rstrip() + "\n    </style>",
            1,
        )
        statuses.append("CSS_ADDED")
    else:
        statuses.append("CSS_ALREADY_PRESENT")

    if UI_MARK not in text:
        anchor = (
            '<h1 class="pc-gv-v18-assignments-title">'
            'Phiếu phân công</h1>'
        )
        count = text.count(anchor)
        if count != 1:
            raise RuntimeError(
                f"Không tìm đúng tiêu đề Phiếu phân công mobile; count={count}."
            )

        text = text.replace(
            anchor,
            anchor + "\n" + HTML_BLOCK.rstrip(),
            1,
        )
        statuses.append("UI_ADDED")
    else:
        statuses.append("UI_ALREADY_PRESENT")

    return text, "+".join(statuses)


def clear_cache():
    for p in APP.rglob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


def verify():
    source = SURVEYS.read_text(encoding="utf-8")
    template = HOUSEHOLDS.read_text(encoding="utf-8")

    ast.parse(source)

    required_source = [
        ROUTE_MARK,
        '@router.post("/{batch_id}/ho-dan/them-mobile")',
        "survey_investigation_team_forms",
        "survey_investigation_team_members",
        "survey_form_investigators",
        "assigned_count != 3",
        "db.commit()",
        "db.rollback()",
    ]
    missing_source = [x for x in required_source if x not in source]
    if missing_source:
        raise RuntimeError(
            "surveys.py sau sửa thiếu: " + repr(missing_source)
        )

    required_ui = [
        UI_MARK,
        CSS_MARK,
        "＋ THÊM HỘ MỚI",
        "TẠO HỘ VÀ NHẬP NHANH",
        "/ho-dan/them-mobile",
        "mobile_add_error",
    ]
    missing_ui = [x for x in required_ui if x not in template]
    if missing_ui:
        raise RuntimeError(
            "households.html sau sửa thiếu: " + repr(missing_ui)
        )

    from jinja2 import Environment
    Environment().parse(template)


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 160)
        log(f, "BATCH 24 - THÊM HỘ MỚI TRÊN GIAO DIỆN ĐIỆN THOẠI GIÁO VIÊN")
        log(f, "HỘ PHÁT SINH TỰ GẮN VÀO ĐÚNG TỔ ĐIỀU TRA 3 CẤP")
        log(f, "CÀI SOURCE ONLY - KHÔNG GHI DATABASE")
        log(f, "=" * 160)

        if not DB.exists() or not SURVEYS.exists() or not HOUSEHOLDS.exists():
            raise RuntimeError("Thiếu DB hoặc source bắt buộc.")

        integrity, fk_count = db_health()
        db_sha_before = sha256_file(DB)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK =", fk_count)

        source_before = SURVEYS.read_text(encoding="utf-8-sig")
        template_before = HOUSEHOLDS.read_text(encoding="utf-8-sig")

        # Khóa nền theo các chức năng Mobile đã chốt.
        for marker in (
            "def them_ho_dan(",
            "SurveyFormInvestigator",
            "survey_investigation_team_forms",
        ):
            if marker not in source_before:
                raise RuntimeError(
                    "surveys.py không đúng nền hiện tại; thiếu " + marker
                )

        for marker in (
            "GV_MOBILE_V18",
            "pc-gv-v18-assignments-title",
            "Phiếu phân công",
            "Nhập nhanh",
        ):
            if marker not in template_before:
                raise RuntimeError(
                    "households.html không đúng nền Mobile hiện tại; thiếu "
                    + marker
                )

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUP_DIR / f"source_truoc_BATCH24_{stamp}"
        backup_root.mkdir(parents=True, exist_ok=False)

        survey_backup = backup_file(SURVEYS, backup_root)
        template_backup = backup_file(HOUSEHOLDS, backup_root)

        log(f, "SOURCE_BACKUP_DIR =", backup_root)

        try:
            source_after, status_source = patch_surveys(source_before)
            template_after, status_template = patch_households(template_before)

            SURVEYS.write_text(source_after, encoding="utf-8")
            HOUSEHOLDS.write_text(template_after, encoding="utf-8")

            py_compile.compile(str(SURVEYS), doraise=True)
            log(f, "PY_COMPILE = PASS")

            verify()
            log(f, "SOURCE_VERIFY = PASS")

            clear_cache()

            log(f, "PATCH surveys.py =", status_source)
            log(f, "PATCH households.html =", status_template)

        except Exception:
            restore_file(SURVEYS, survey_backup)
            restore_file(HOUSEHOLDS, template_backup)
            clear_cache()
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        db_sha_after = sha256_file(DB)
        if db_sha_after != db_sha_before:
            restore_file(SURVEYS, survey_backup)
            restore_file(HOUSEHOLDS, template_backup)
            clear_cache()
            raise RuntimeError(
                "DB SHA thay đổi trong lúc cài source; đã khôi phục source."
            )

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "BATCH_24_SUCCESS = YES")
        log(f, "")
        log(f, "NGHIEP_VU = GV điện thoại -> Phiếu phân công -> + THÊM HỘ MỚI.")
        log(f, "SAU_LUU = Hệ thống tạo hộ + phiếu, gắn đúng tổ 3 cấp, rồi mở thẳng Nhập nhanh.")
        log(f, "AN_TOAN = Nếu GV chưa thuộc đúng 1 tổ MN+TH+THCS hoặc hộ bị trùng, hệ thống dừng và không ghi.")
        log(f, "=" * 160)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 160)
                log(f, "BATCH_24_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 160)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    sys.exit(rc)
