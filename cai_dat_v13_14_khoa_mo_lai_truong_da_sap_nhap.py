# -*- coding: utf-8 -*-
'''
V13.14 - KHÔNG CHO MỞ LẠI TRƯỜNG NGUỒN ĐÃ SÁP NHẬP

- Hiển thị "Đã sáp nhập".
- Hiển thị "→ mã · tên trường đích".
- Bỏ nút "Mở lại" cho trường nguồn đã sáp nhập.
- Backend chặn POST cố tình mở lại.
- Trường bị khóa thông thường vẫn giữ "Mở lại".

KHÔNG sửa database, Plan JSON, school_id, mã/tên trường hay dữ liệu sáp nhập.
'''

from __future__ import annotations

import ast
import json
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
ROUTER = APP / "routers" / "schools.py"
TEMPLATE = APP / "templates" / "schools" / "list.html"
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
EXPORTS = ROOT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_source_v13_14_khoa_truong_sap_nhap_{STAMP}"
REPORT = ROOT / f"bao_cao_cai_v13_14_{STAMP}.txt"

EXPECTED_SOURCE_COUNT = 495

ROUTER_HELPER_START = "# === V13_14_MERGED_SOURCE_HELPER_START ==="
ROUTER_HELPER_END = "# === V13_14_MERGED_SOURCE_HELPER_END ==="
ROUTER_LIST_START = "# === V13_14_MERGED_SOURCE_LIST_START ==="
ROUTER_LIST_END = "# === V13_14_MERGED_SOURCE_LIST_END ==="
ROUTER_GUARD_START = "# === V13_14_MERGED_SOURCE_REOPEN_GUARD_START ==="
ROUTER_GUARD_END = "# === V13_14_MERGED_SOURCE_REOPEN_GUARD_END ==="

TPL_NAME_START = "{# === V13_14_MERGED_SOURCE_NAME_START === #}"
TPL_NAME_END = "{# === V13_14_MERGED_SOURCE_NAME_END === #}"
TPL_STATUS_START = "{# === V13_14_MERGED_SOURCE_STATUS_START === #}"
TPL_STATUS_END = "{# === V13_14_MERGED_SOURCE_STATUS_END === #}"
TPL_ACTION_START = "{# === V13_14_MERGED_SOURCE_ACTION_START === #}"
TPL_ACTION_END = "{# === V13_14_MERGED_SOURCE_ACTION_END === #}"


HELPER_BLOCK = "\n".join([
    "# === V13_14_MERGED_SOURCE_HELPER_START ===",
    "def _v1314_completed_merger_source_map(",
    "    db: Session,",
    ") -> dict[int, dict[str, Any]]:",
    "    json_module = __import__('json')",
    "    pairs: dict[int, int] = {}",
    "    plan_path = APP_DIR.parent / 'data' / 'school_merger_approved_plans.json'",
    "",
    "    try:",
    "        payload = json_module.loads(plan_path.read_text(encoding='utf-8'))",
    "        for plan in payload.get('plans') or []:",
    "            if not isinstance(plan, dict):",
    "                continue",
    "            if str(plan.get('status') or '').upper() != 'COMPLETED':",
    "                continue",
    "            try:",
    "                target_id = int(plan.get('target_school_id') or 0)",
    "            except (TypeError, ValueError):",
    "                target_id = 0",
    "            if target_id <= 0:",
    "                continue",
    "            for raw_source_id in plan.get('source_school_ids') or []:",
    "                try:",
    "                    source_id = int(raw_source_id)",
    "                except (TypeError, ValueError):",
    "                    continue",
    "                if source_id <= 0 or source_id == target_id:",
    "                    continue",
    "                previous = pairs.get(source_id)",
    "                if previous is not None and previous != target_id:",
    "                    raise RuntimeError(",
    "                        f'Trường nguồn {source_id} có nhiều target: {previous}/{target_id}'",
    "                    )",
    "                pairs[source_id] = target_id",
    "    except FileNotFoundError:",
    "        pass",
    "",
    "    try:",
    "        rows = db.connection().exec_driver_sql(",
    "            'SELECT target_school_id, source_school_ids_json '",
    "            'FROM school_merger_operations ORDER BY id'",
    "        ).fetchall()",
    "        for row in rows:",
    "            try:",
    "                target_id = int(row[0] or 0)",
    "                source_ids = json_module.loads(row[1] or '[]')",
    "            except Exception:",
    "                continue",
    "            if target_id <= 0:",
    "                continue",
    "            for raw_source_id in source_ids or []:",
    "                try:",
    "                    source_id = int(raw_source_id)",
    "                except (TypeError, ValueError):",
    "                    continue",
    "                if source_id <= 0 or source_id == target_id:",
    "                    continue",
    "                previous = pairs.get(source_id)",
    "                if previous is not None and previous != target_id:",
    "                    raise RuntimeError(",
    "                        f'Audit source {source_id} có nhiều target: {previous}/{target_id}'",
    "                    )",
    "                pairs[source_id] = target_id",
    "    except Exception:",
    "        pass",
    "",
    "    if not pairs:",
    "        return {}",
    "",
    "    target_ids = sorted(set(pairs.values()))",
    "    targets = db.scalars(",
    "        select(School).where(School.id.in_(target_ids))",
    "    ).all()",
    "    target_by_id = {int(item.id): item for item in targets}",
    "",
    "    result: dict[int, dict[str, Any]] = {}",
    "    for source_id, target_id in pairs.items():",
    "        target = target_by_id.get(target_id)",
    "        result[source_id] = {",
    "            'target_school_id': target_id,",
    "            'target_code': str(target.code or '') if target is not None else '',",
    "            'target_name': (",
    "                str(target.name or '')",
    "                if target is not None",
    "                else f'school_id={target_id}'",
    "            ),",
    "        }",
    "    return result",
    "# === V13_14_MERGED_SOURCE_HELPER_END ===",
])


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def backup_files() -> None:
    for path in (ROUTER, TEMPLATE):
        dst = BACKUP / path.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)

    (BACKUP / "manifest.json").write_text(
        json.dumps(
            {
                "version": "V13.14",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "files": [
                    str(ROUTER.relative_to(ROOT)),
                    str(TEMPLATE.relative_to(ROOT)),
                ],
                "database_changed": False,
                "plan_json_changed": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def restore_files() -> None:
    for path in (ROUTER, TEMPLATE):
        src = BACKUP / path.relative_to(ROOT)
        if src.exists():
            shutil.copy2(src, path)


def preflight_merger_state() -> dict:
    payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    pairs: dict[int, int] = {}

    for plan in payload.get("plans") or []:
        if not isinstance(plan, dict):
            continue
        if str(plan.get("status") or "").upper() != "COMPLETED":
            continue

        target_id = int(plan.get("target_school_id") or 0)
        if target_id <= 0:
            continue

        for value in plan.get("source_school_ids") or []:
            source_id = int(value)
            if source_id <= 0 or source_id == target_id:
                continue
            previous = pairs.get(source_id)
            if previous is not None and previous != target_id:
                raise RuntimeError(
                    f"source={source_id} có hai target {previous}/{target_id}"
                )
            pairs[source_id] = target_id

    if len(pairs) != EXPECTED_SOURCE_COUNT:
        raise RuntimeError(
            f"Plan COMPLETED có {len(pairs)} source; cần {EXPECTED_SOURCE_COUNT}."
        )

    con = sqlite3.connect(str(DB_PATH), timeout=60)
    try:
        integrity = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk = len(
            con.execute("PRAGMA foreign_key_check").fetchall()
        )
        if integrity.lower() != "ok" or fk:
            raise RuntimeError(
                f"DB không đạt: integrity={integrity}, FK={fk}"
            )

        source_ids = sorted(pairs)
        target_ids = sorted(set(pairs.values()))
        source_active = 0
        target_inactive = 0

        for start in range(0, len(source_ids), 700):
            chunk = source_ids[start:start + 700]
            marks = ",".join("?" for _ in chunk)
            source_active += int(
                con.execute(
                    f"SELECT COUNT(*) FROM schools "
                    f"WHERE id IN ({marks}) AND is_active=1",
                    chunk,
                ).fetchone()[0]
                or 0
            )

        for start in range(0, len(target_ids), 700):
            chunk = target_ids[start:start + 700]
            marks = ",".join("?" for _ in chunk)
            target_inactive += int(
                con.execute(
                    f"SELECT COUNT(*) FROM schools "
                    f"WHERE id IN ({marks}) AND is_active=0",
                    chunk,
                ).fetchone()[0]
                or 0
            )

        if source_active:
            raise RuntimeError(
                f"Còn {source_active} source merger đang active."
            )
        if target_inactive:
            raise RuntimeError(
                f"Có {target_inactive} target merger đang inactive."
            )

        return {
            "source_count": len(source_ids),
            "target_count": len(target_ids),
            "source_active": source_active,
            "target_inactive": target_inactive,
            "integrity": integrity,
            "fk": fk,
        }
    finally:
        con.close()


def function_bounds(source: str, name: str) -> tuple[int, int]:
    tree = ast.parse(source)
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == name
        ),
        None,
    )
    if node is None:
        raise RuntimeError(f"Không tìm thấy hàm {name}.")

    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    start_line = (
        min([d.lineno for d in node.decorator_list] + [node.lineno])
        - 1
    )
    return offsets[start_line], offsets[node.end_lineno]


def patch_router(source: str) -> tuple[str, str]:
    if (
        ROUTER_HELPER_START in source
        and ROUTER_LIST_START in source
        and ROUTER_GUARD_START in source
    ):
        return source, "ALREADY_INSTALLED"

    if any(
        x in source
        for x in [
            ROUTER_HELPER_START,
            ROUTER_HELPER_END,
            ROUTER_LIST_START,
            ROUTER_LIST_END,
            ROUTER_GUARD_START,
            ROUTER_GUARD_END,
        ]
    ):
        raise RuntimeError("Router chỉ có một phần marker V13.14.")

    # Chèn helper trước route đầu tiên.
    pos = source.find("@router.get(")
    if pos < 0:
        raise RuntimeError("Không tìm thấy @router.get trong schools.py.")

    source = source[:pos] + HELPER_BLOCK + "\n\n\n" + source[pos:]

    # Danh sách trường: truyền mapping source -> target cho template.
    start, end = function_bounds(source, "danh_sach_truong")
    block = source[start:end]

    anchor = "    return templates.TemplateResponse("
    if block.count(anchor) != 1:
        raise RuntimeError(
            "danh_sach_truong không có đúng 1 TemplateResponse."
        )

    inject = (
        "    # === V13_14_MERGED_SOURCE_LIST_START ===\n"
        "    sap_nhap_nguon_map = _v1314_completed_merger_source_map(db)\n"
        "    # === V13_14_MERGED_SOURCE_LIST_END ===\n\n"
    )
    block = block.replace(anchor, inject + anchor, 1)

    context_anchor = '"co_quyen_quan_ly": can_manage,'
    if block.count(context_anchor) != 1:
        raise RuntimeError(
            "Không tìm thấy context co_quyen_quan_ly."
        )
    block = block.replace(
        context_anchor,
        context_anchor
        + '\n            "sap_nhap_nguon_map": sap_nhap_nguon_map,',
        1,
    )
    source = source[:start] + block + source[end:]

    # Chặn backend mở lại source merger.
    start, end = function_bounds(source, "khoa_hoac_mo_truong")
    block = source[start:end]

    toggle_anchor = "    school.is_active = not school.is_active"
    if block.count(toggle_anchor) != 1:
        raise RuntimeError("Không tìm đúng dòng toggle school.is_active.")

    guard = (
        "    # === V13_14_MERGED_SOURCE_REOPEN_GUARD_START ===\n"
        "    v1314_merged_sources = _v1314_completed_merger_source_map(db)\n"
        "    if school_id in v1314_merged_sources and not school.is_active:\n"
        "        target = v1314_merged_sources[school_id]\n"
        "        raise HTTPException(\n"
        "            status_code=409,\n"
        "            detail=(\n"
        "                'Trường nguồn đã sáp nhập không được phép mở lại. '\n"
        "                f\"Trường đích: {target.get('target_name') or target.get('target_school_id')}.\"\n"
        "            ),\n"
        "        )\n"
        "    # === V13_14_MERGED_SOURCE_REOPEN_GUARD_END ===\n"
    )

    block = block.replace(toggle_anchor, guard + toggle_anchor, 1)
    source = source[:start] + block + source[end:]

    ast.parse(source)
    return source, "INSTALLED"


def patch_template(source: str) -> tuple[str, str]:
    if (
        TPL_NAME_START in source
        and TPL_STATUS_START in source
        and TPL_ACTION_START in source
    ):
        return source, "ALREADY_INSTALLED"

    if any(
        x in source
        for x in [
            TPL_NAME_START,
            TPL_NAME_END,
            TPL_STATUS_START,
            TPL_STATUS_END,
            TPL_ACTION_START,
            TPL_ACTION_END,
        ]
    ):
        raise RuntimeError("Template chỉ có một phần marker V13.14.")

    old_name = "<td>{{ truong.name }}</td>"
    new_name = (
        "<td>"
        "{# === V13_14_MERGED_SOURCE_NAME_START === #}"
        "{% set v1314_merge = (sap_nhap_nguon_map|default({})).get(truong.id) %}"
        "{{ truong.name }}"
        "{% if v1314_merge %}"
        "<br><small style=\"color:#6b7280;font-weight:700;\">"
        "→ {{ v1314_merge.target_code }}"
        "{% if v1314_merge.target_code %} · {% endif %}"
        "{{ v1314_merge.target_name }}"
        "</small>"
        "{% endif %}"
        "{# === V13_14_MERGED_SOURCE_NAME_END === #}"
        "</td>"
    )
    if source.count(old_name) != 1:
        raise RuntimeError("Không tìm đúng ô Tên trường.")
    source = source.replace(old_name, new_name, 1)

    old_status = (
        "<td>{% if truong.is_active %}"
        "<span class=\"status-badge status-active\">Đang hoạt động</span>"
        "{% else %}"
        "<span class=\"status-badge status-locked\">Đã khóa</span>"
        "{% endif %}</td>"
    )
    new_status = (
        "<td>"
        "{# === V13_14_MERGED_SOURCE_STATUS_START === #}"
        "{% if v1314_merge %}"
        "<span class=\"status-badge status-locked\">Đã sáp nhập</span>"
        "{% elif truong.is_active %}"
        "<span class=\"status-badge status-active\">Đang hoạt động</span>"
        "{% else %}"
        "<span class=\"status-badge status-locked\">Đã khóa</span>"
        "{% endif %}"
        "{# === V13_14_MERGED_SOURCE_STATUS_END === #}"
        "</td>"
    )
    if source.count(old_status) != 1:
        raise RuntimeError("Không tìm đúng khối Trạng thái.")
    source = source.replace(old_status, new_status, 1)

    old_action = (
        "<a class=\"button button-small button-edit\" "
        "href=\"/truong/{{ truong.id }}/sua\">Sửa</a>"
        "<form method=\"post\" action=\"/truong/{{ truong.id }}/khoa-mo\">"
        "<button class=\"button button-small "
        "{% if truong.is_active %}button-lock{% else %}button-unlock{% endif %}\" "
        "type=\"submit\">"
        "{% if truong.is_active %}Khóa{% else %}Mở lại{% endif %}"
        "</button></form>"
    )
    new_action = (
        "{# === V13_14_MERGED_SOURCE_ACTION_START === #}"
        "<a class=\"button button-small button-edit\" "
        "href=\"/truong/{{ truong.id }}/sua\">Sửa</a>"
        "{% if v1314_merge %}"
        "<span class=\"button button-small\" "
        "style=\"cursor:not-allowed;opacity:.75;background:#eef2f7;color:#64748b;\">"
        "Không mở lại"
        "</span>"
        "{% else %}"
        "<form method=\"post\" action=\"/truong/{{ truong.id }}/khoa-mo\">"
        "<button class=\"button button-small "
        "{% if truong.is_active %}button-lock{% else %}button-unlock{% endif %}\" "
        "type=\"submit\">"
        "{% if truong.is_active %}Khóa{% else %}Mở lại{% endif %}"
        "</button></form>"
        "{% endif %}"
        "{# === V13_14_MERGED_SOURCE_ACTION_END === #}"
    )
    if source.count(old_action) != 1:
        raise RuntimeError("Không tìm đúng khối Khóa/Mở lại.")
    source = source.replace(old_action, new_action, 1)

    return source, "INSTALLED"


def verify_router(source: str) -> None:
    ast.parse(source)
    for marker in [
        ROUTER_HELPER_START,
        ROUTER_HELPER_END,
        ROUTER_LIST_START,
        ROUTER_LIST_END,
        ROUTER_GUARD_START,
        ROUTER_GUARD_END,
        '"sap_nhap_nguon_map": sap_nhap_nguon_map',
        "status_code=409",
        "Trường nguồn đã sáp nhập không được phép mở lại",
    ]:
        if marker not in source:
            raise RuntimeError(f"Router thiếu marker: {marker}")


def verify_template(source: str) -> None:
    for marker in [
        TPL_NAME_START,
        TPL_NAME_END,
        TPL_STATUS_START,
        TPL_STATUS_END,
        TPL_ACTION_START,
        TPL_ACTION_END,
        "Đã sáp nhập",
        "Không mở lại",
        "v1314_merge.target_name",
    ]:
        if marker not in source:
            raise RuntimeError(f"Template thiếu marker: {marker}")

    from jinja2 import Environment
    Environment().parse(source)


def clear_cache() -> int:
    count = 0
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)
            count += 1
    return count


def main() -> int:
    print("=" * 108)
    print("V13.14 - KHÓA MỞ LẠI TRƯỜNG ĐÃ SÁP NHẬP")
    print("=" * 108)

    for path in (ROUTER, TEMPLATE, DB_PATH, PLAN_FILE):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    state = preflight_merger_state()

    print("")
    print("PREFLIGHT PASS")
    print(f" - Source merger: {state['source_count']}")
    print(f" - Target unique: {state['target_count']}")
    print(f" - Source active: {state['source_active']}")
    print(f" - Target inactive: {state['target_inactive']}")
    print(f" - DB integrity: {state['integrity']}")
    print(f" - DB FK: {state['fk']}")

    router_before = read_text(ROUTER)
    template_before = read_text(TEMPLATE)

    router_after, router_mode = patch_router(router_before)
    template_after, template_mode = patch_template(template_before)

    if (
        router_mode == "ALREADY_INSTALLED"
        and template_mode == "ALREADY_INSTALLED"
    ):
        verify_router(router_before)
        verify_template(template_before)
        print("")
        print("V13.14 đã có sẵn - không chèn lặp.")
        print("Database: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        return 0

    if (
        router_mode == "ALREADY_INSTALLED"
        or template_mode == "ALREADY_INSTALLED"
    ):
        raise RuntimeError(
            "V13.14 chỉ có ở một file; dừng để tránh lệch source."
        )

    backup_files()

    try:
        verify_router(router_after)
        verify_template(template_after)

        ROUTER.write_text(router_after, encoding="utf-8")
        TEMPLATE.write_text(template_after, encoding="utf-8")

        py_compile.compile(str(ROUTER), doraise=True)
        verify_router(read_text(ROUTER))
        verify_template(read_text(TEMPLATE))
        cache_count = clear_cache()
    except Exception:
        restore_files()
        raise

    state_after = preflight_merger_state()

    report_lines = [
        "V13.14 - KHÔNG CHO MỞ LẠI TRƯỜNG NGUỒN ĐÃ SÁP NHẬP",
        "=" * 80,
        "",
        "STATUS=SUCCESS",
        "",
        f"Source merger={state_after['source_count']}",
        f"Target unique={state_after['target_count']}",
        f"Source active={state_after['source_active']}",
        f"Target inactive={state_after['target_inactive']}",
        f"DB integrity={state_after['integrity']}",
        f"DB FK={state_after['fk']}",
        "",
        "UI:",
        "- Source merger: Đã sáp nhập",
        "- Hiện → mã · tên trường đích",
        "- Không còn nút Mở lại",
        "- Trường khóa thường vẫn Mở lại",
        "",
        "BACKEND:",
        "- POST mở lại source merger bị chặn HTTP 409",
        "",
        f"Backup={BACKUP}",
        f"Router mode={router_mode}",
        f"Template mode={template_mode}",
        f"Cache removed={cache_count}",
        "",
        "Database=KHÔNG THAY ĐỔI",
        "Plan JSON=KHÔNG THAY ĐỔI",
        "Dữ liệu sáp nhập=KHÔNG THAY ĐỔI",
    ]
    REPORT.write_text("\n".join(report_lines), encoding="utf-8")

    print("")
    print("=" * 108)
    print("V13.14 CÀI ĐẶT THÀNH CÔNG")
    print("=" * 108)
    print("495 source merger: Đã sáp nhập")
    print("Nút Mở lại source merger: ĐÃ BỎ")
    print("Backend mở lại source merger: ĐÃ CHẶN")
    print("Trường khóa thông thường: VẪN CÓ Mở lại")
    print(f"Backup: {BACKUP}")
    print(f"Báo cáo: {REPORT}")
    print("Database: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")
    print("")
    print("Khởi động lại Uvicorn và Ctrl+F5.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("")
        print("=" * 108)
        print("V13.14 DỪNG AN TOÀN")
        print("=" * 108)
        print(repr(exc))
        print("Nếu lỗi xảy ra sau backup, source được tự khôi phục.")
        print("Database: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
