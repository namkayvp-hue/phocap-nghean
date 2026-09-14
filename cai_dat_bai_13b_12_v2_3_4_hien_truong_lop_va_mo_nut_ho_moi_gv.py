# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

YEAR_TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
TEAM_ROUTER = APP / "routers" / "survey_team_registration.py"
HOUSEHOLDS_TEMPLATE = APP / "templates" / "surveys" / "households.html"
ACCESS = APP / "access_control.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_4_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_4_{STAMP}.txt"

OLD_HIDE_START = "<!-- === BAI_13B_11_13_3_4_HIDE_LOCATION_FOR_XMC_START === -->"
OLD_HIDE_END = "<!-- === BAI_13B_11_13_3_4_HIDE_LOCATION_FOR_XMC_END === -->"
HIDE5_START = "<!-- === BAI_13B_11_13_3_4_1_HIDE_ONLY_5_XMC_FIELDS_START === -->"
HIDE5_END = "<!-- === BAI_13B_11_13_3_4_1_HIDE_ONLY_5_XMC_FIELDS_END === -->"

CAN_CREATE_OLD = """    can_create = bool(
        batch
        and not bool(batch.get("is_locked"))
        and str(batch.get("status") or "") != "DA_KET_THUC"
        and team
        and len(members) == 3
        and assignments
    )
"""

CAN_CREATE_NEW = """    # === BAI_13B_12_V2_3_4_PERMISSION_BUTTON_START ===
    # Hiển thị nút khi giáo viên thuộc tổ 3 người đã SENT và đợt còn hoạt động.
    # Không dùng "đã có giao địa bàn" làm điều kiện ẨN nút.
    can_create = bool(
        batch
        and not bool(batch.get("is_locked"))
        and str(batch.get("status") or "") != "DA_KET_THUC"
        and team
        and len(members) == 3
    )
    # === BAI_13B_12_V2_3_4_PERMISSION_BUTTON_END ===
"""

SAFETY_HTML = """
<!-- === BAI_13B_12_V2_3_4_ALWAYS_SHOW_CURRENT_SCHOOL_CLASS === -->
<style>
.b13113341-hidden { display: block !important; }
</style>
<script>
(function () {
    "use strict";

    function reveal(selector) {
        const element = document.querySelector(selector);
        if (!element) return;

        const group =
            element.closest(".form-group")
            || element.closest(".field-group")
            || element.closest(".form-field")
            || element.parentElement;

        if (!group) return;

        group.classList.remove("b13113341-hidden");
        group.hidden = false;
        group.style.removeProperty("display");
    }

    function showCurrentStudyFields() {
        [
            "#commune_search",
            "#commune_selected",
            '[name="commune_id"]',
            "#school_search",
            "#school_selected",
            '[name="school_id"]',
            "#class_search",
            "#class_selected",
            '[name="class_id"]',
            '[name="school_name_reported"]',
            '[name="class_name_reported"]'
        ].forEach(reveal);
    }

    document.addEventListener("DOMContentLoaded", function () {
        const xmc = document.getElementById("is_literacy_target");
        if (xmc) {
            xmc.addEventListener("change", showCurrentStudyFields);
        }
        showCurrentStudyFields();
        window.setTimeout(showCurrentStudyFields, 150);
        window.setTimeout(showCurrentStudyFields, 550);
    });
})();
</script>
"""

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")

def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")

def backup_file(path: Path) -> None:
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

def restore_file(path: Path) -> None:
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)

def backup_db() -> None:
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(DB_BACKUP))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

def restore_db() -> None:
    if not DB_BACKUP.exists():
        return
    src = sqlite3.connect(str(DB_BACKUP))
    dst = sqlite3.connect(str(DB))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())

        counts = {}
        for table in (
            "survey_people",
            "survey_person_year_records",
            "households",
            "survey_forms",
            "survey_investigation_teams",
            "survey_investigation_team_members",
            "survey_team_area_assignments",
        ):
            try:
                counts[table] = int(
                    con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                )
            except sqlite3.Error:
                counts[table] = None

        teams = []
        try:
            teams = [
                dict(row)
                for row in con.execute(
                    """
                    SELECT
                        t.survey_batch_id,
                        t.team_number,
                        t.status,
                        COUNT(DISTINCT tm.user_id) AS member_count,
                        COUNT(DISTINCT ta.area_id) AS area_count
                    FROM survey_investigation_teams t
                    LEFT JOIN survey_investigation_team_members tm
                      ON tm.team_id = t.id
                    LEFT JOIN survey_team_area_assignments ta
                      ON ta.team_id = t.id
                    GROUP BY
                        t.survey_batch_id,
                        t.id,
                        t.team_number,
                        t.status
                    ORDER BY
                        t.survey_batch_id,
                        t.team_number
                    """
                ).fetchall()
            ]
        except sqlite3.Error:
            pass

        return {
            "integrity": integrity,
            "fk_count": fk_count,
            "counts": counts,
            "teams": teams,
        }
    finally:
        con.close()

def remove_block(source: str, start_marker: str, end_marker: str):
    if start_marker not in source:
        return source, False

    start = source.find(start_marker)
    end = source.find(end_marker, start)
    if end < 0:
        raise RuntimeError("Có marker đầu nhưng thiếu marker cuối: " + start_marker)

    end += len(end_marker)
    return source[:start] + source[end:], True

def patch_year_template(source: str):
    changes = []

    source, removed = remove_block(source, OLD_HIDE_START, OLD_HIDE_END)
    if removed:
        changes.append("Đã bỏ block cũ ẩn Xã/Trường/Lớp khi thuộc XMC.")

    source, removed = remove_block(source, HIDE5_START, HIDE5_END)
    if removed:
        changes.append("Đã bỏ block cũ chỉ giữ 5 trường khi thuộc XMC.")

    marker = "BAI_13B_12_V2_3_4_ALWAYS_SHOW_CURRENT_SCHOOL_CLASS"
    if marker not in source:
        pos = source.rfind("</body>")
        if pos < 0:
            raise RuntimeError("year_records.html thiếu </body>.")
        source = source[:pos] + SAFETY_HTML + source[pos:]
        changes.append("Đã thêm bảo vệ để Trường/Lớp hiện tại luôn hiển thị.")

    return source, changes

def patch_team_router(source: str):
    changes = []

    if "BAI_13B_12_V2_3_4_PERMISSION_BUTTON_START" in source:
        return source, ["Nút hộ mới đã có logic V2.3.4."]

    if CAN_CREATE_OLD not in source:
        raise RuntimeError(
            "Không tìm thấy block can_create V2.2/V2.3 đúng bản dự kiến."
        )

    source = source.replace(CAN_CREATE_OLD, CAN_CREATE_NEW, 1)
    changes.append(
        "Đã bỏ điều kiện assignments khỏi việc HIỂN THỊ nút hộ mới."
    )
    return source, changes

def verify_source() -> None:
    template = read_text(YEAR_TEMPLATE)
    team = read_text(TEAM_ROUTER)
    households = read_text(HOUSEHOLDS_TEMPLATE)

    for forbidden in (OLD_HIDE_START, HIDE5_START, "applyOnlyFiveXmcFields"):
        if forbidden in template:
            raise RuntimeError("Vẫn còn logic ẩn Trường/Lớp: " + forbidden)

    for token in (
        "Trường hiện tại",
        "Lớp hiện tại",
        'name="school_id"',
        'name="class_id"',
        'name="school_name_reported"',
        'name="class_name_reported"',
        "BAI_13B_12_V2_3_4_ALWAYS_SHOW_CURRENT_SCHOOL_CLASS",
    ):
        if token not in template:
            raise RuntimeError("Template thiếu: " + token)

    if "BAI_13B_12_V2_3_4_PERMISSION_BUTTON_START" not in team:
        raise RuntimeError("Router tổ chưa có logic V2.3.4.")

    if '@router.get("/nhap-ho-moi/{batch_id}/quyen")' not in team:
        raise RuntimeError("Không thấy endpoint quyền nhập hộ mới.")

    for token in (
        "BAI_13B_12_V2_2_NEW_HOUSE_BUTTON",
        ".b1322-new-household-link",
        "/nhap-ho-moi/{{ batch.id }}/quyen",
    ):
        if token not in households:
            raise RuntimeError("households.html thiếu: " + token)

    ast.parse(team)
    py_compile.compile(str(TEAM_ROUTER), doraise=True)

    env = Environment()
    env.parse(template)
    env.parse(households)

def main() -> int:
    print("=" * 122)
    print(
        "BÀI 13B-12 V2.3.4 - HIỆN TRƯỜNG/LỚP HIỆN TẠI "
        "+ MỞ ĐÚNG NÚT HỘ MỚI GIÁO VIÊN"
    )
    print("=" * 122)

    for path in (DB, YEAR_TEMPLATE, TEAM_ROUTER, HOUSEHOLDS_TEMPLATE, ACCESS):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra.")
        return 3

    template = read_text(YEAR_TEMPLATE)
    team = read_text(TEAM_ROUTER)
    households = read_text(HOUSEHOLDS_TEMPLATE)
    access = read_text(ACCESS)

    if "BAI_13B_12_V2_3_3_XMC_SELECTED_YEAR_UI_START" not in template:
        print("DỪNG AN TOÀN: chưa thấy nền V2.3.3.")
        return 4

    if "BAI_13B_12_V2_3_2_EXTRACT_BATCH_ID_START" not in access:
        print("DỪNG AN TOÀN: chưa thấy sửa lỗi batch_id đã tích hợp ở V2.3.3.")
        return 5

    try:
        template_new, template_changes = patch_year_template(template)
        team_new, team_changes = patch_team_router(team)

        ast.parse(team_new)
        Environment().parse(template_new)
        Environment().parse(households)

    except Exception as exc:
        print("DỪNG AN TOÀN TRƯỚC KHI GHI FILE:")
        print(type(exc).__name__ + ":", exc)
        return 6

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    for path in (YEAR_TEMPLATE, TEAM_ROUTER, HOUSEHOLDS_TEMPLATE):
        backup_file(path)
    backup_db()

    print("Backup:", BACKUP)

    try:
        write_text(YEAR_TEMPLATE, template_new)
        write_text(TEAM_ROUTER, team_new)

        verify_source()

        after = db_state()

        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")
        if before["counts"] != after["counts"]:
            raise RuntimeError(
                "V2.3.4 không được phép thay đổi số dòng database."
            )

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)

        for path in (YEAR_TEMPLATE, TEAM_ROUTER, HOUSEHOLDS_TEMPLATE):
            restore_file(path)
        restore_db()

        print("ĐÃ KHÔI PHỤC.")
        return 9

    lines = [
        "=" * 122,
        "BÁO CÁO CÀI BÀI 13B-12 V2.3.4",
        "=" * 122,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "TRƯỜNG/LỚP:",
    ]
    lines.extend("- " + x for x in template_changes)
    lines.extend([
        "- Thuộc phạm vi XMC không còn làm ẩn Trường/Lớp hiện tại.",
        "",
        "NÚT HỘ MỚI:",
    ])
    lines.extend("- " + x for x in team_changes)
    lines.extend([
        "- Giáo viên vẫn phải thuộc tổ SENT đủ 3 thành viên.",
        "- Nếu tổ chưa có địa bàn: nút vẫn hiện, nhưng màn hình nhập hộ không có địa bàn để chọn nên không thể lưu hộ.",
        "",
        "TỔ HIỆN CÓ:",
    ])

    for row in after["teams"]:
        lines.append(
            f"  batch={row['survey_batch_id']} | "
            f"tổ={row['team_number']} | "
            f"status={row['status']} | "
            f"members={row['member_count']} | "
            f"areas={row['area_count']}"
        )

    lines.extend([
        "",
        f"integrity_check: {after['integrity']}",
        f"foreign_key_check: {after['fk_count']} lỗi",
        f"Backup: {BACKUP}",
    ])

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    print()
    print("=" * 122)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.3.4")
    print("=" * 122)
    print(" - Trường/Lớp hiện tại: luôn hiển thị.")
    print(" - XMC không còn ẩn Trường/Lớp.")
    print(" - Nút hộ mới không còn bị ẩn chỉ vì thiếu giao địa bàn.")
    print(" - Không thay đổi dữ liệu database.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
