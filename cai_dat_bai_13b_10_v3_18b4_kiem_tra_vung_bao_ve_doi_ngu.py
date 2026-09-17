from __future__ import annotations

import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
ROUTER = APP / "routers" / "data_tools.py"
TEMPLATE = APP / "templates" / "data_tools" / "survey_cleanup.html"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_source_bai_13b_10_v3_18b4_{STAMP}"
MARK = "BAI_13B_10_V3_18B4_PROTECTED_DOMAINS"

OLD_COUNT = 'def _count_preserved(con: sqlite3.Connection) -> dict[str, int]:\n    result = {\n        "communes": 0,\n        "schools": 0,\n        "users": 0,\n        "students": 0,\n        "staff": 0,\n    }\n\n    for table, key in (\n        ("communes", "communes"),\n        ("schools", "schools"),\n        ("users", "users"),\n        ("students", "students"),\n        ("staff", "staff"),\n    ):\n        if _table_exists(con, table):\n            result[key] = _scalar(\n                con,\n                f"SELECT COUNT(*) FROM {_quote_ident(table)}",\n            )\n\n    return result\n'
NEW_COUNT = '# === BAI_13B_10_V3_18B4_PROTECTED_DOMAINS ===\nPROTECTED_EXACT_TABLES = {\n    "communes",\n    "schools",\n    "users",\n    "roles",\n    "school_years",\n    "students",\n    "student_year_records",\n    "student_school_year_records",\n    "staff_members",\n    "staff_year_records",\n    "school_staff_year_summaries",\n    "school_structured_report_inputs",\n    "school_network_year_data",\n    "school_network_year_datas",\n}\n\nPROTECTED_PREFIXES = (\n    "staff_",\n    "school_staff_",\n    "school_structured_report_",\n    "school_network_",\n)\n\n\ndef _is_protected_domain_table(table: str) -> bool:\n    name = str(table or "").strip().lower()\n\n    if name in PROTECTED_EXACT_TABLES:\n        return True\n\n    return any(\n        name.startswith(prefix)\n        for prefix in PROTECTED_PREFIXES\n    )\n\n\ndef _protected_target_tables(\n    targets: dict[str, set[int]],\n) -> list[str]:\n    return sorted(\n        table\n        for table, ids in targets.items()\n        if ids and _is_protected_domain_table(table)\n    )\n\n\ndef _count_preserved(con: sqlite3.Connection) -> dict[str, int]:\n    result = {\n        "communes": 0,\n        "schools": 0,\n        "users": 0,\n        "students": 0,\n        "staff": 0,\n        "staff_year_records": 0,\n        "structured_staff_forms": 0,\n    }\n\n    for table, key in (\n        ("communes", "communes"),\n        ("schools", "schools"),\n        ("users", "users"),\n        ("students", "students"),\n        ("staff_members", "staff"),\n        ("staff_year_records", "staff_year_records"),\n    ):\n        if _table_exists(con, table):\n            result[key] = _scalar(\n                con,\n                f"SELECT COUNT(*) FROM {_quote_ident(table)}",\n            )\n\n    if _table_exists(con, "school_structured_report_inputs"):\n        cols = _column_names(\n            con,\n            "school_structured_report_inputs",\n        )\n        if "form_code" in cols:\n            result["structured_staff_forms"] = _scalar(\n                con,\n                \'\'\'\n                SELECT COUNT(*)\n                FROM school_structured_report_inputs\n                WHERE UPPER(COALESCE(form_code, \'\')) IN (\n                    \'TH_01_GV\',\n                    \'THCS_01_GV\'\n                )\n                \'\'\',\n            )\n\n    return result\n'
OLD_PROPAGATE = '    # Từ household riêng sẽ tự kéo survey_people và các child phụ thuộc.\n    targets = _propagate_children(\n        con,\n        targets,\n    )\n\n    forms = len(targets.get("survey_forms", set()))\n'
NEW_PROPAGATE = '    # Từ household riêng sẽ tự kéo survey_people và các child phụ thuộc.\n    targets = _propagate_children(\n        con,\n        targets,\n    )\n\n    protected_targets = _protected_target_tables(targets)\n    protection_ok = not protected_targets\n\n    forms = len(targets.get("survey_forms", set()))\n'
OLD_RETURN = '        "table_counts": table_counts,\n        "targets": targets,\n        "preserved": _count_preserved(con),\n    }\n'
NEW_RETURN = '        "table_counts": table_counts,\n        "targets": targets,\n        "preserved": _count_preserved(con),\n        "protected_target_tables": protected_targets,\n        "protection_ok": protection_ok,\n    }\n'
OLD_SAFE = '    year_plan_public["safe_to_execute"] = (\n        year_plan_public["batch_count"]\n        == EXPECTED_BATCH_COUNT\n    )\n'
NEW_SAFE = '    year_plan_public["safe_to_execute"] = (\n        year_plan_public["batch_count"]\n        == EXPECTED_BATCH_COUNT\n        and year_plan_public.get("protection_ok") is True\n    )\n'
OLD_EXEC_TARGETS = '        targets = live_plan["targets"]\n        order = _delete_order(\n            con,\n            targets,\n        )\n'
NEW_EXEC_TARGETS = '        if not live_plan.get("protection_ok"):\n            protected = ", ".join(\n                live_plan.get("protected_target_tables") or []\n            )\n            raise RuntimeError(\n                "VÙNG BẢO VỆ KHÔNG ĐẠT. "\n                "Kế hoạch DELETE chạm bảng cần giữ: "\n                + protected\n            )\n\n        targets = live_plan["targets"]\n        order = _delete_order(\n            con,\n            targets,\n        )\n'
OLD_STAFF_CARD = '                <div class="card">\n                    <span>Đội ngũ</span>\n                    <strong>\n                        {{ year_plan.preserved.staff }}\n                    </strong>\n                </div>\n'
NEW_STAFF_CARD = '                <div class="card">\n                    <span>Đội ngũ (hồ sơ người)</span>\n                    <strong>\n                        {{ year_plan.preserved.staff }}\n                    </strong>\n                </div>\n'
OLD_SAFE_BLOCK = '            <div class="safe">\n                Không dọn: xã/phường, trường, tài khoản,\n                học sinh, đội ngũ, danh mục, năm học,\n                mã nguồn và các bản ghi\n                <code>survey_batches</code>.\n            </div>\n        </section>\n'
NEW_SAFE_BLOCK = '            <div class="safe">\n                Không dọn: xã/phường, trường, tài khoản,\n                học sinh, đội ngũ, danh mục, năm học,\n                mã nguồn và các bản ghi\n                <code>survey_batches</code>.\n                <br><br>\n                <strong>Kiểm kê đội ngũ thực tế:</strong>\n                {{ year_plan.preserved.staff }} hồ sơ người\n                · {{ year_plan.preserved.staff_year_records }}\n                bản ghi đội ngũ theo năm\n                · {{ year_plan.preserved.structured_staff_forms }}\n                biểu TH-01-GV / THCS-01-GV chuyên biệt.\n            </div>\n\n            {% if year_plan.protection_ok %}\n            <div class="safe">\n                <strong>✓ KIỂM TRA VÙNG BẢO VỆ: ĐẠT.</strong>\n                Không có bảng xã/phường, trường, tài khoản,\n                học sinh, đội ngũ, dữ liệu mạng lưới hoặc\n                biểu đội ngũ chuyên biệt nào nằm trong kế hoạch DELETE.\n            </div>\n            {% else %}\n            <div class="warn">\n                <strong>✗ KIỂM TRA VÙNG BẢO VỆ: KHÔNG ĐẠT.</strong>\n                Phát hiện bảng cần giữ trong kế hoạch DELETE:\n                {% for table in year_plan.protected_target_tables %}\n                    <code>{{ table }}</code>{% if not loop.last %}, {% endif %}\n                {% endfor %}\n                . Nút dọn dữ liệu đã bị khóa.\n            </div>\n            {% endif %}\n        </section>\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    for src in (ROUTER, TEMPLATE):
        dst = BACKUP / src.relative_to(PROJECT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def restore() -> None:
    for target in (ROUTER, TEMPLATE):
        src = BACKUP / target.relative_to(PROJECT)
        if src.exists():
            shutil.copy2(src, target)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch_router(text: str) -> str:
    if MARK in text:
        return text

    required = [
        OLD_COUNT,
        OLD_PROPAGATE,
        OLD_RETURN,
        OLD_SAFE,
        OLD_EXEC_TARGETS,
    ]

    missing = [
        str(index + 1)
        for index, block in enumerate(required)
        if block not in text
    ]

    if missing:
        raise RuntimeError(
            "data_tools.py không đúng nền V3.18B3 ở các điểm: "
            + ", ".join(missing)
        )

    text = text.replace(OLD_COUNT, NEW_COUNT, 1)
    text = text.replace(OLD_PROPAGATE, NEW_PROPAGATE, 1)
    text = text.replace(OLD_RETURN, NEW_RETURN, 1)
    text = text.replace(OLD_SAFE, NEW_SAFE, 1)
    text = text.replace(OLD_EXEC_TARGETS, NEW_EXEC_TARGETS, 1)

    return text


def patch_template(text: str) -> str:
    if "KIỂM TRA VÙNG BẢO VỆ: ĐẠT." in text:
        return text

    if OLD_STAFF_CARD not in text:
        raise RuntimeError("Không tìm thấy card Đội ngũ hiện tại.")

    if OLD_SAFE_BLOCK not in text:
        raise RuntimeError(
            "Không tìm thấy khối dữ liệu hệ thống giữ nguyên."
        )

    text = text.replace(OLD_STAFF_CARD, NEW_STAFF_CARD, 1)
    text = text.replace(OLD_SAFE_BLOCK, NEW_SAFE_BLOCK, 1)
    return text


def verify() -> None:
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )

    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(APP / "templates"))
    )
    env.get_template("data_tools/survey_cleanup.html")

    router = read_text(ROUTER)
    template = read_text(TEMPLATE)

    for item in (
        MARK,
        "staff_members",
        "staff_year_records",
        "school_staff_year_summaries",
        "school_structured_report_inputs",
        "school_network_",
        "protected_target_tables",
        "protection_ok",
        "VÙNG BẢO VỆ KHÔNG ĐẠT",
    ):
        if item not in router:
            raise RuntimeError(f"Router sau cài thiếu: {item}")

    for item in (
        "Đội ngũ (hồ sơ người)",
        "bản ghi đội ngũ theo năm",
        "biểu TH-01-GV / THCS-01-GV chuyên biệt",
        "KIỂM TRA VÙNG BẢO VỆ: ĐẠT.",
        "Nút dọn dữ liệu đã bị khóa.",
    ):
        if item not in template:
            raise RuntimeError(f"Template sau cài thiếu: {item}")


def main() -> int:
    print("=" * 108)
    print(
        "BÀI 13B-10 V3.18B4 - "
        "KIỂM TRA VÙNG BẢO VỆ ĐỘI NGŨ TRƯỚC KHI DỌN"
    )
    print("=" * 108)
    print()
    print("Cài bản này KHÔNG xóa dữ liệu.")
    print("Bổ sung đếm đúng đội ngũ và chặn cứng nếu kế hoạch DELETE")
    print("chạm các bảng xã/trường/tài khoản/học sinh/đội ngũ/mạng lưới.")
    print()

    if not ROUTER.exists() or not TEMPLATE.exists():
        raise RuntimeError(
            "Không tìm thấy data_tools.py hoặc survey_cleanup.html."
        )

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup()
    print("Backup source:", BACKUP)

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

        print()
        print("CÀI ĐẶT BÀI 13B-10 V3.18B4 THÀNH CÔNG")
        print("Khởi động lại Uvicorn và Ctrl+F5.")
        print("CHƯA BẤM NÚT DỌN cho tới khi kiểm tra màn hình.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC V3.18B3...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE TRƯỚC V3.18B4.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
