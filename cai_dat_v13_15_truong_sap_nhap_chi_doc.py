# -*- coding: utf-8 -*-
r'''
V13.15 - TRƯỜNG NGUỒN ĐÃ SÁP NHẬP = HỒ SƠ CHỈ ĐỌC

- Trường nguồn đã sáp nhập: nút Sửa -> Xem.
- GET /truong/{id}/sua của source merger mở trang chỉ xem.
- POST /truong/{id}/sua của source merger bị chặn HTTP 409.
- Trường đích và trường khóa thông thường vẫn sửa bình thường.

KHÔNG sửa database, Plan JSON, school_id, mã/tên/xã/địa chỉ hay dữ liệu sáp nhập.
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
LIST_TPL = APP / "templates" / "schools" / "list.html"
READONLY_TPL = APP / "templates" / "schools" / "merged_readonly.html"
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
EXPORTS = ROOT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_source_v13_15_truong_sap_nhap_chi_doc_{STAMP}"
REPORT = ROOT / f"bao_cao_cai_v13_15_{STAMP}.txt"

EXPECTED_SOURCE_COUNT = 495

R14_HELPER = "# === V13_14_MERGED_SOURCE_HELPER_START ==="
R14_GUARD = "# === V13_14_MERGED_SOURCE_REOPEN_GUARD_START ==="
T14_ACTION_START = "{# === V13_14_MERGED_SOURCE_ACTION_START === #}"
T14_ACTION_END = "{# === V13_14_MERGED_SOURCE_ACTION_END === #}"

R15_GET_START = "# === V13_15_MERGED_SOURCE_READONLY_GET_START ==="
R15_GET_END = "# === V13_15_MERGED_SOURCE_READONLY_GET_END ==="
R15_POST_START = "# === V13_15_MERGED_SOURCE_EDIT_GUARD_START ==="
R15_POST_END = "# === V13_15_MERGED_SOURCE_EDIT_GUARD_END ==="
T15_ACTION_START = "{# === V13_15_MERGED_SOURCE_READONLY_ACTION_START === #}"
T15_ACTION_END = "{# === V13_15_MERGED_SOURCE_READONLY_ACTION_END === #}"
READONLY_MARKER = "<!-- === V13_15_MERGED_SOURCE_READONLY_PAGE === -->"


READONLY_TEMPLATE = r'''<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Xem trường đã sáp nhập</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <style>
        body { background:#f4f7fb; color:#17324d; margin:0; }
        .v1315-wrap { width:min(1100px, calc(100% - 32px)); margin:28px auto 50px; }
        .v1315-card {
            background:#fff; border:1px solid #dbe5ef; border-radius:16px;
            box-shadow:0 8px 28px rgba(18,56,94,.08); padding:24px;
        }
        .v1315-head {
            display:flex; justify-content:space-between; gap:18px; align-items:flex-start;
            margin-bottom:22px; flex-wrap:wrap;
        }
        .v1315-eyebrow {
            margin:0 0 7px; color:#1976d2; font-size:12px; font-weight:800;
            letter-spacing:.08em; text-transform:uppercase;
        }
        .v1315-head h1 { margin:0; font-size:28px; line-height:1.2; }
        .v1315-note {
            margin:10px 0 0; color:#5d7185; max-width:760px; line-height:1.55;
        }
        .v1315-badge {
            display:inline-flex; align-items:center; border-radius:999px;
            padding:7px 11px; font-size:13px; font-weight:800;
            background:#ffe9ee; color:#b42337;
        }
        .v1315-grid {
            display:grid; grid-template-columns:repeat(2,minmax(0,1fr));
            gap:14px;
        }
        .v1315-field {
            border:1px solid #e1e8f0; border-radius:11px; padding:13px 14px;
            background:#fbfdff; min-height:68px;
        }
        .v1315-field.full { grid-column:1/-1; }
        .v1315-label {
            display:block; margin-bottom:5px; color:#698095; font-size:12px;
            font-weight:800; text-transform:uppercase; letter-spacing:.04em;
        }
        .v1315-value { font-size:15px; font-weight:700; word-break:break-word; }
        .v1315-target {
            margin-top:20px; padding:17px; border-radius:12px;
            border:1px solid #b9dcff; background:#f0f8ff;
        }
        .v1315-target strong { color:#0c5ca8; }
        .v1315-actions {
            margin-top:22px; display:flex; gap:10px; flex-wrap:wrap;
        }
        .v1315-btn {
            display:inline-flex; min-height:40px; align-items:center; justify-content:center;
            padding:0 15px; border-radius:9px; text-decoration:none; font-weight:800;
            border:1px solid #cbd8e5; background:#fff; color:#245072;
        }
        .v1315-btn.primary { background:#1976d2; color:#fff; border-color:#1976d2; }
        .v1315-lock {
            margin-top:16px; padding:12px 14px; border-radius:10px;
            background:#fff8e7; color:#785400; font-weight:700; line-height:1.5;
        }
        @media (max-width:700px) {
            .v1315-grid { grid-template-columns:1fr; }
            .v1315-field.full { grid-column:auto; }
        }
    </style>
</head>
<body>
<!-- === V13_15_MERGED_SOURCE_READONLY_PAGE === -->
{% include "partials/dropdown_menu_v1.html" %}

<main class="v1315-wrap">
    <section class="v1315-card">
        <div class="v1315-head">
            <div>
                <p class="v1315-eyebrow">Hồ sơ lịch sử sau sáp nhập</p>
                <h1>{{ truong.name }}</h1>
                <p class="v1315-note">
                    Trường này là trường nguồn đã hoàn thành sáp nhập.
                    Hồ sơ được giữ để tra cứu lịch sử và không còn được chỉnh sửa.
                </p>
            </div>
            <span class="v1315-badge">Đã sáp nhập</span>
        </div>

        <div class="v1315-grid">
            <div class="v1315-field">
                <span class="v1315-label">Mã trường nguồn</span>
                <div class="v1315-value">{{ truong.code }}</div>
            </div>
            <div class="v1315-field">
                <span class="v1315-label">Tên trường nguồn</span>
                <div class="v1315-value">{{ truong.name }}</div>
            </div>
            <div class="v1315-field">
                <span class="v1315-label">Xã/phường</span>
                <div class="v1315-value">
                    {{ truong.commune.name if truong.commune else '—' }}
                </div>
            </div>
            <div class="v1315-field">
                <span class="v1315-label">Trạng thái</span>
                <div class="v1315-value">Đã sáp nhập · Chỉ đọc</div>
            </div>
            <div class="v1315-field full">
                <span class="v1315-label">Địa chỉ lịch sử</span>
                <div class="v1315-value">{{ truong.address or '—' }}</div>
            </div>
        </div>

        <div class="v1315-target">
            <span class="v1315-label">Trường đích sau sáp nhập</span>
            <strong>
                {{ merger_target.target_code }}
                {% if merger_target.target_code %} · {% endif %}
                {{ merger_target.target_name }}
            </strong>
        </div>

        <div class="v1315-lock">
            🔒 Hồ sơ trường nguồn đã được khóa đối với thao tác sửa thông tin
            và mở lại. Các nghiệp vụ hiện hành thực hiện tại trường đích.
        </div>

        <div class="v1315-actions">
            <a class="v1315-btn primary" href="/truong">← Danh mục trường</a>
            <a class="v1315-btn"
               href="/truong/{{ merger_target.target_school_id }}/sua">
                Xem/Sửa trường đích
            </a>
        </div>
    </section>
</main>
</body>
</html>
'''


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def preflight_state() -> dict:
    payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    pairs: dict[int, int] = {}

    for plan in payload.get("plans") or []:
        if not isinstance(plan, dict):
            continue
        if str(plan.get("status") or "").upper() != "COMPLETED":
            continue

        target = int(plan.get("target_school_id") or 0)
        if target <= 0:
            continue

        for raw in plan.get("source_school_ids") or []:
            source = int(raw)
            if source <= 0 or source == target:
                continue
            old = pairs.get(source)
            if old is not None and old != target:
                raise RuntimeError(
                    f"source {source} có hai target {old}/{target}"
                )
            pairs[source] = target

    if len(pairs) != EXPECTED_SOURCE_COUNT:
        raise RuntimeError(
            f"Completed merger source={len(pairs)}, cần {EXPECTED_SOURCE_COUNT}."
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
                f"DB lỗi: integrity={integrity}, FK={fk}"
            )

        source_ids = sorted(pairs)
        source_active = 0

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

        if source_active:
            raise RuntimeError(
                f"Còn {source_active} source merger active."
            )

        return {
            "source_count": len(source_ids),
            "source_active": source_active,
            "integrity": integrity,
            "fk": fk,
        }
    finally:
        con.close()


def backup_files() -> dict:
    BACKUP.mkdir(parents=True, exist_ok=False)

    manifest = {}
    for path in (ROUTER, LIST_TPL, READONLY_TPL):
        rel = path.relative_to(ROOT)
        existed = path.exists()
        manifest[str(rel)] = existed

        if existed:
            dst = BACKUP / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)

    (BACKUP / "manifest.json").write_text(
        json.dumps(
            {
                "version": "V13.15",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "files": manifest,
                "database_changed": False,
                "plan_json_changed": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def restore_files(manifest: dict) -> None:
    for rel_text, existed in manifest.items():
        rel = Path(rel_text)
        target = ROOT / rel

        if existed:
            src = BACKUP / rel
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        elif target.exists():
            target.unlink()


def function_bounds(source: str, name: str) -> tuple[int, int]:
    tree = ast.parse(source)
    node = next(
        (
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == name
        ),
        None,
    )
    if node is None:
        raise RuntimeError(f"Không tìm thấy hàm {name}.")

    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    first_line = min(
        [d.lineno for d in node.decorator_list] + [node.lineno]
    ) - 1

    return offsets[first_line], offsets[node.end_lineno]


def patch_router(source: str) -> tuple[str, str]:
    if R15_GET_START in source and R15_POST_START in source:
        return source, "ALREADY_INSTALLED"

    if R15_GET_START in source or R15_POST_START in source:
        raise RuntimeError("Router chỉ có một phần marker V13.15.")

    if R14_HELPER not in source or R14_GUARD not in source:
        raise RuntimeError(
            "Chưa thấy nền V13.14 trong schools.py."
        )

    school_anchor = (
        "    if school is None:\n"
        "        raise HTTPException(status_code=404, detail=\"Không tìm thấy trường.\")\n"
    )

    start, end = function_bounds(source, "form_sua_truong")
    block = source[start:end]

    if block.count(school_anchor) != 1:
        raise RuntimeError(
            "form_sua_truong không đúng cấu trúc dự kiến."
        )

    get_guard = (
        school_anchor
        + "\n"
        + "    # === V13_15_MERGED_SOURCE_READONLY_GET_START ===\n"
        + "    v1315_merger_map = _v1314_completed_merger_source_map(db)\n"
        + "    v1315_merger_target = v1315_merger_map.get(school_id)\n"
        + "    if v1315_merger_target is not None:\n"
        + "        return templates.TemplateResponse(\n"
        + "            request=request,\n"
        + "            name=\"schools/merged_readonly.html\",\n"
        + "            context={\n"
        + "                \"nguoi_dung\": lay_actor(request),\n"
        + "                \"truong\": school,\n"
        + "                \"merger_target\": v1315_merger_target,\n"
        + "            },\n"
        + "        )\n"
        + "    # === V13_15_MERGED_SOURCE_READONLY_GET_END ===\n"
    )

    block = block.replace(
        school_anchor,
        get_guard,
        1,
    )
    source = source[:start] + block + source[end:]

    start, end = function_bounds(source, "cap_nhat_truong")
    block = source[start:end]

    if block.count(school_anchor) != 1:
        raise RuntimeError(
            "cap_nhat_truong không đúng cấu trúc dự kiến."
        )

    post_guard = (
        school_anchor
        + "\n"
        + "    # === V13_15_MERGED_SOURCE_EDIT_GUARD_START ===\n"
        + "    v1315_merger_target = _v1314_completed_merger_source_map(db).get(school_id)\n"
        + "    if v1315_merger_target is not None:\n"
        + "        raise HTTPException(\n"
        + "            status_code=409,\n"
        + "            detail=(\n"
        + "                \"Trường nguồn đã sáp nhập là hồ sơ chỉ đọc, không được sửa. \"\n"
        + "                f\"Trường đích: {v1315_merger_target.get('target_name') or v1315_merger_target.get('target_school_id')}.\"\n"
        + "            ),\n"
        + "        )\n"
        + "    # === V13_15_MERGED_SOURCE_EDIT_GUARD_END ===\n"
    )

    block = block.replace(
        school_anchor,
        post_guard,
        1,
    )
    source = source[:start] + block + source[end:]

    ast.parse(source)
    return source, "INSTALLED"


def patch_list_template(source: str) -> tuple[str, str]:
    if T15_ACTION_START in source and T15_ACTION_END in source:
        return source, "ALREADY_INSTALLED"

    if T15_ACTION_START in source or T15_ACTION_END in source:
        raise RuntimeError("list.html chỉ có một phần marker V13.15.")

    if T14_ACTION_START not in source or T14_ACTION_END not in source:
        raise RuntimeError(
            "Chưa thấy action block V13.14 trong list.html."
        )

    start = source.find(T14_ACTION_START)
    end = source.find(T14_ACTION_END, start)

    if start < 0 or end < 0:
        raise RuntimeError(
            "Không xác định được action block V13.14."
        )

    end += len(T14_ACTION_END)
    current = source[start:end]

    for token in [
        "v1314_merge",
        "Không mở lại",
        "/truong/{{ truong.id }}/sua",
    ]:
        if token not in current:
            raise RuntimeError(
                f"Action block V13.14 thiếu: {token}"
            )

    new_block = (
        T14_ACTION_START
        + T15_ACTION_START
        + "{% if v1314_merge %}"
        + "<a class=\"button button-small button-edit\" "
          "href=\"/truong/{{ truong.id }}/sua\">Xem</a>"
        + "<span class=\"button button-small\" "
          "style=\"cursor:not-allowed;opacity:.75;background:#eef2f7;color:#64748b;\">"
          "Không mở lại</span>"
        + "{% else %}"
        + "<a class=\"button button-small button-edit\" "
          "href=\"/truong/{{ truong.id }}/sua\">Sửa</a>"
        + "<form method=\"post\" action=\"/truong/{{ truong.id }}/khoa-mo\">"
        + "<button class=\"button button-small "
          "{% if truong.is_active %}button-lock{% else %}button-unlock{% endif %}\" "
          "type=\"submit\">"
        + "{% if truong.is_active %}Khóa{% else %}Mở lại{% endif %}"
        + "</button></form>"
        + "{% endif %}"
        + T15_ACTION_END
        + T14_ACTION_END
    )

    return (
        source[:start]
        + new_block
        + source[end:],
        "INSTALLED",
    )


def verify_router(source: str) -> None:
    ast.parse(source)

    for token in [
        R14_HELPER,
        R14_GUARD,
        R15_GET_START,
        R15_GET_END,
        R15_POST_START,
        R15_POST_END,
        'name="schools/merged_readonly.html"',
        "Trường nguồn đã sáp nhập là hồ sơ chỉ đọc",
        "status_code=409",
    ]:
        if token not in source:
            raise RuntimeError(
                f"Router thiếu token: {token}"
            )


def verify_list(source: str) -> None:
    for token in [
        T14_ACTION_START,
        T14_ACTION_END,
        T15_ACTION_START,
        T15_ACTION_END,
        ">Xem</a>",
        "Không mở lại",
    ]:
        if token not in source:
            raise RuntimeError(
                f"List template thiếu token: {token}"
            )

    from jinja2 import Environment
    Environment().parse(source)


def verify_readonly_template(source: str) -> None:
    for token in [
        READONLY_MARKER,
        "Hồ sơ lịch sử sau sáp nhập",
        "Đã sáp nhập · Chỉ đọc",
        "merger_target.target_name",
        "Xem/Sửa trường đích",
    ]:
        if token not in source:
            raise RuntimeError(
                f"Readonly template thiếu token: {token}"
            )

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
    print("=" * 110)
    print("V13.15 - TRƯỜNG ĐÃ SÁP NHẬP = CHỈ ĐỌC")
    print("=" * 110)

    for path in (
        ROUTER,
        LIST_TPL,
        DB_PATH,
        PLAN_FILE,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    state = preflight_state()

    router_before = read_text(ROUTER)
    list_before = read_text(LIST_TPL)

    if (
        R14_HELPER not in router_before
        or R14_GUARD not in router_before
    ):
        raise RuntimeError(
            "V13.14 chưa có đủ trong schools.py."
        )

    print("")
    print("PREFLIGHT PASS")
    print(
        f" - Completed source merger: "
        f"{state['source_count']}"
    )
    print(
        f" - Source active: "
        f"{state['source_active']}"
    )
    print(
        f" - DB integrity: "
        f"{state['integrity']}"
    )
    print(
        f" - DB FK: "
        f"{state['fk']}"
    )
    print(" - V13.14 backend/UI: CÓ")

    router_after, router_mode = patch_router(
        router_before
    )
    list_after, list_mode = patch_list_template(
        list_before
    )

    readonly_mode = (
        "ALREADY_INSTALLED"
        if (
            READONLY_TPL.exists()
            and READONLY_MARKER in read_text(READONLY_TPL)
        )
        else "INSTALLED"
    )

    if (
        router_mode == "ALREADY_INSTALLED"
        and list_mode == "ALREADY_INSTALLED"
        and readonly_mode == "ALREADY_INSTALLED"
    ):
        verify_router(router_before)
        verify_list(list_before)
        verify_readonly_template(
            read_text(READONLY_TPL)
        )

        print("")
        print(
            "V13.15 đã cài sẵn - không chèn lặp."
        )
        print("Database: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        return 0

    if (
        router_mode == "ALREADY_INSTALLED"
        or list_mode == "ALREADY_INSTALLED"
        or readonly_mode == "ALREADY_INSTALLED"
    ):
        raise RuntimeError(
            "V13.15 đang ở trạng thái cài dở giữa các file."
        )

    verify_router(router_after)
    verify_list(list_after)
    verify_readonly_template(READONLY_TEMPLATE)

    manifest = backup_files()

    try:
        ROUTER.write_text(
            router_after,
            encoding="utf-8",
        )
        LIST_TPL.write_text(
            list_after,
            encoding="utf-8",
        )
        READONLY_TPL.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        READONLY_TPL.write_text(
            READONLY_TEMPLATE,
            encoding="utf-8",
        )

        py_compile.compile(
            str(ROUTER),
            doraise=True,
        )

        verify_router(read_text(ROUTER))
        verify_list(read_text(LIST_TPL))
        verify_readonly_template(
            read_text(READONLY_TPL)
        )

        from jinja2 import Environment, FileSystemLoader

        env = Environment(
            loader=FileSystemLoader(
                str(APP / "templates")
            )
        )
        env.get_template("schools/list.html")
        env.get_template(
            "schools/merged_readonly.html"
        )

        cache_count = clear_cache()

    except Exception:
        restore_files(manifest)
        raise

    state_after = preflight_state()

    report = f'''V13.15 - TRƯỜNG NGUỒN ĐÃ SÁP NHẬP = CHỈ ĐỌC
================================================================================

STATUS=SUCCESS

SOURCE MERGER
- Completed source = {state_after['source_count']}
- Source active = {state_after['source_active']}

DATABASE
- integrity = {state_after['integrity']}
- FK = {state_after['fk']}
- Database changed = NO
- Plan JSON changed = NO

UI
- Source merger: nút Sửa -> Xem
- Source merger: vẫn Không mở lại
- Trang Xem là hồ sơ chỉ đọc
- Có chỉ dẫn trường đích
- Trường thường/target: vẫn Sửa bình thường

BACKEND
- POST /truong/{{school_id}}/sua của source merger -> HTTP 409
- GET /truong/{{school_id}}/sua của source merger -> readonly page

FILES
- app/routers/schools.py
- app/templates/schools/list.html
- app/templates/schools/merged_readonly.html

Backup:
{BACKUP}

router_mode={router_mode}
list_mode={list_mode}
readonly_mode={readonly_mode}
cache_removed={cache_count}

Database=KHÔNG THAY ĐỔI
Plan JSON=KHÔNG THAY ĐỔI
Dữ liệu sáp nhập=KHÔNG THAY ĐỔI
'''

    REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print("")
    print("=" * 110)
    print("V13.15 CÀI ĐẶT THÀNH CÔNG")
    print("=" * 110)
    print("495 trường nguồn merger: CHỈ ĐỌC")
    print(
        "Nút Sửa source merger: "
        "ĐÃ ĐỔI THÀNH XEM"
    )
    print(
        "POST sửa source merger: "
        "ĐÃ CHẶN HTTP 409"
    )
    print(
        "Không mở lại: GIỮ NGUYÊN V13.14"
    )
    print(
        "Trường đích/trường thường: "
        "VẪN SỬA BÌNH THƯỜNG"
    )
    print(f"Backup: {BACKUP}")
    print(f"Báo cáo: {REPORT}")
    print("Database: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")
    print("")
    print(
        "Khởi động lại Uvicorn và Ctrl+F5."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("")
        print("=" * 110)
        print("V13.15 DỪNG AN TOÀN")
        print("=" * 110)
        print(repr(exc))
        print(
            "Nếu đã backup, source được "
            "tự khôi phục khi lỗi."
        )
        print("Database: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
