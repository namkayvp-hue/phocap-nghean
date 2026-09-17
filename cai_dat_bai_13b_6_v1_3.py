from __future__ import annotations

import json
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()

ROUTER = PROJECT / "app" / "routers" / "report_inputs.py"
TEMPLATE = PROJECT / "app" / "templates" / "report_inputs" / "structured_school_form.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_6_v1_3_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

MN_SCOPE_BLOCK = '\n\n# === BAI_13B_6_V1_3_MN_SCOPE_START ===\ndef _looks_like_preschool_school(school: School) -> bool:\n    """Nhận diện trường/cơ sở mầm non từ tên hoặc mã đơn vị."""\n    text = _pc_norm(\n        " ".join([\n            str(getattr(school, "name", "") or ""),\n            str(getattr(school, "code", "") or ""),\n        ])\n    )\n    words = set(text.split())\n    return (\n        "MAM NON" in text\n        or "MAU GIAO" in text\n        or "NHA TRE" in text\n        or "NHOM TRE" in text\n        or "LOP MAM NON" in text\n        or "MN" in words\n    )\n\n\ndef _mn_scope(\n    db: Session,\n    request: Request,\n    school_year_id: int | None,\n    commune_id: int | None,\n    school_id: int | None,\n) -> dict[str, Any]:\n    """\n    Phạm vi riêng cho MN-01-GV và MN-01-CSVC.\n\n    Sau khi nhập mạng lưới Tiểu học/THCS, các trường đó cùng nằm trong bảng\n    schools. Hai màn hình Mầm non phải loại chúng khỏi ô chọn Trường.\n    """\n    scope = _load_scope(\n        db,\n        request,\n        school_year_id,\n        commune_id,\n        school_id,\n    )\n\n    non_mn_ids = {\n        int(value)\n        for value in db.scalars(\n            select(SchoolNetworkYearData.school_id)\n            .where(SchoolNetworkYearData.level_code.in_(["TH", "THCS"]))\n            .distinct()\n        ).all()\n    }\n\n    filtered = [\n        school\n        for school in list(scope.get("schools") or [])\n        if _looks_like_preschool_school(school)\n        or int(school.id) not in non_mn_ids\n    ]\n\n    valid_ids = {int(s.id) for s in filtered}\n    selected_school_id = scope.get("selected_school_id")\n\n    if (\n        selected_school_id is not None\n        and int(selected_school_id) not in valid_ids\n    ):\n        selected_school_id = None\n\n    selected_school = next(\n        (\n            s for s in filtered\n            if int(s.id) == int(selected_school_id or 0)\n        ),\n        None,\n    )\n\n    scope["schools"] = filtered\n    scope["selected_school_id"] = selected_school_id\n    scope["selected_school"] = selected_school\n\n    if selected_school is not None:\n        scope["scope_label"] = f"Trường {selected_school.name}"\n\n    return scope\n# === BAI_13B_6_V1_3_MN_SCOPE_END ===\n'
STAFF_DETAIL_BLOCK = '\n\n# === BAI_13B_6_V1_3_STAFF_DETAIL_START ===\ndef _structured_staff_row_matches_level(\n    row: StaffYearRecord,\n    level: str,\n) -> bool:\n    source_level = str(\n        getattr(row, "source_level", "") or ""\n    ).strip().upper()\n\n    teaching_level = str(\n        getattr(row, "teaching_level", "") or ""\n    ).strip().upper()\n\n    if level == "TH":\n        if source_level == "TH":\n            return True\n        if teaching_level in {"TIEU_HOC", "LIEN_CAP_TH_THCS"}:\n            return True\n        # Hồ sơ cũ chưa có trường source_level vẫn cho hiển thị\n        # nếu không xác định rõ là THCS.\n        return source_level not in {"THCS"}\n\n    if level == "THCS":\n        if source_level == "THCS":\n            return True\n        if teaching_level in {"THCS", "LIEN_CAP_TH_THCS"}:\n            return True\n        return source_level not in {"TH"}\n\n    return True\n\n\ndef _structured_staff_detail_rows(\n    db: Session,\n    *,\n    school_id: int,\n    target_year_id: int,\n    level: str,\n) -> tuple[list[StaffYearRecord], str | None]:\n    """\n    Lấy danh sách tên nhân sự để hiển thị ngay dưới biểu TH-01-GV/\n    THCS-01-GV.\n\n    Ưu tiên năm đang nhập. Nếu năm đang nhập chưa có hồ sơ chi tiết,\n    lấy năm dữ liệu gần nhất không vượt quá năm đang nhập\n    (ví dụ 2025-2026 làm tham chiếu cho 2026-2027).\n    """\n    rows = list(\n        db.scalars(\n            select(StaffYearRecord)\n            .where(\n                StaffYearRecord.school_id == school_id,\n                StaffYearRecord.is_active.is_(True),\n                StaffYearRecord.status_code == "DANG_LAM_VIEC",\n            )\n            .options(\n                selectinload(StaffYearRecord.staff_member),\n                selectinload(StaffYearRecord.school_year),\n            )\n        ).all()\n    )\n\n    rows = [\n        row\n        for row in rows\n        if _structured_staff_row_matches_level(row, level)\n    ]\n\n    if not rows:\n        return [], None\n\n    by_year: dict[int, list[StaffYearRecord]] = {}\n    for row in rows:\n        by_year.setdefault(int(row.school_year_id), []).append(row)\n\n    if int(target_year_id) in by_year:\n        chosen_year_id = int(target_year_id)\n    else:\n        target_year = db.get(SchoolYear, target_year_id)\n        target_start = _structured_year_start(\n            getattr(target_year, "code", None)\n        )\n\n        candidates: list[tuple[int, int]] = []\n        for year_id in by_year:\n            year = db.get(SchoolYear, year_id)\n            start = _structured_year_start(\n                getattr(year, "code", None)\n            )\n            valid = 1 if (\n                not target_start or start <= target_start\n            ) else 0\n            candidates.append((valid, start, year_id))\n\n        _valid, _start, chosen_year_id = max(candidates)\n\n    chosen_rows = list(by_year.get(chosen_year_id, []))\n\n    position_rank = {\n        "CBQL": 0,\n        "GIAO_VIEN": 1,\n        "NHAN_VIEN": 2,\n    }\n\n    chosen_rows.sort(\n        key=lambda row: (\n            position_rank.get(\n                str(row.position_group or "").upper(),\n                9,\n            ),\n            _pc_norm(\n                getattr(\n                    getattr(row, "staff_member", None),\n                    "full_name",\n                    "",\n                )\n            ),\n            int(row.id),\n        )\n    )\n\n    chosen_year = db.get(SchoolYear, chosen_year_id)\n    chosen_year_code = (\n        getattr(chosen_year, "code", None)\n        if chosen_year is not None\n        else None\n    )\n\n    return chosen_rows, chosen_year_code\n# === BAI_13B_6_V1_3_STAFF_DETAIL_END ===\n'
STAFF_CSS = '\n        /* === BAI_13B_6_V1_3_STAFF_TABLE_CSS_START === */\n        .staff-detail-head{\n            display:flex;\n            justify-content:space-between;\n            gap:12px;\n            align-items:flex-start;\n            flex-wrap:wrap;\n            margin-bottom:12px\n        }\n        .staff-detail-head h2{margin:0}\n        .staff-detail-meta{\n            color:var(--muted);\n            font-size:13px;\n            font-weight:700;\n            line-height:1.45\n        }\n        .staff-table-wrap{\n            width:100%;\n            overflow:auto;\n            border:1px solid var(--line);\n            border-radius:12px;\n            background:#fff\n        }\n        .staff-table{\n            width:100%;\n            min-width:980px;\n            border-collapse:collapse\n        }\n        .staff-table th,\n        .staff-table td{\n            padding:10px 9px;\n            border-bottom:1px solid #e3edf5;\n            text-align:left;\n            vertical-align:top;\n            line-height:1.35\n        }\n        .staff-table th{\n            position:sticky;\n            top:0;\n            z-index:1;\n            background:#e8f1f9;\n            color:#17324d;\n            font-size:13px;\n            font-weight:900\n        }\n        .staff-table td{\n            font-size:13px\n        }\n        .staff-table tr:last-child td{\n            border-bottom:0\n        }\n        .staff-name{\n            min-width:170px;\n            font-weight:900;\n            color:#17324d\n        }\n        .staff-badge{\n            display:inline-block;\n            padding:4px 7px;\n            border-radius:999px;\n            background:#edf4fa;\n            font-size:11px;\n            font-weight:900;\n            white-space:nowrap\n        }\n        .staff-empty{\n            padding:14px;\n            border-radius:10px;\n            background:#f7fafc;\n            color:var(--muted);\n            line-height:1.5\n        }\n        /* === BAI_13B_6_V1_3_STAFF_TABLE_CSS_END === */\n'
STAFF_HTML = '\n    {% if catalog.kind == \'staff\' %}\n    <!-- === BAI_13B_6_V1_3_STAFF_TABLE_START === -->\n    <section class="panel" id="danh-sach-nhan-su">\n        <div class="staff-detail-head">\n            <div>\n                <h2>Danh sách nhân sự của trường</h2>\n                <div class="staff-detail-meta">\n                    Hiển thị CBQL, giáo viên và nhân viên đang làm việc.\n                    {% if staff_detail_year %}\n                    Nguồn chi tiết: năm học <strong>{{ staff_detail_year }}</strong>.\n                    {% endif %}\n                    {% if selected_year and staff_detail_year and selected_year.code != staff_detail_year %}\n                    Đây là danh sách tham chiếu để rà soát cho năm học {{ selected_year.code }}.\n                    {% endif %}\n                </div>\n            </div>\n            {% if staff_detail_rows %}\n            <span class="staff-badge">{{ staff_detail_rows|length }} nhân sự</span>\n            {% endif %}\n        </div>\n\n        {% if staff_detail_rows %}\n        <div class="staff-table-wrap">\n            <table class="staff-table">\n                <thead>\n                    <tr>\n                        <th>STT</th>\n                        <th>Họ và tên</th>\n                        <th>Vị trí</th>\n                        <th>Chức vụ</th>\n                        <th>Môn dạy</th>\n                        <th>Trình độ</th>\n                        <th>Hình thức</th>\n                        <th>Trạng thái</th>\n                    </tr>\n                </thead>\n                <tbody>\n                    {% for row in staff_detail_rows %}\n                    <tr>\n                        <td>{{ loop.index }}</td>\n                        <td class="staff-name">\n                            {{ row.staff_member.full_name if row.staff_member else \'—\' }}\n                        </td>\n                        <td>\n                            {{ staff_position_labels.get(row.position_group, row.position_group or \'—\') }}\n                        </td>\n                        <td>{{ row.position_title or \'—\' }}</td>\n                        <td>{{ row.teaching_subject or \'—\' }}</td>\n                        <td>\n                            {{ qualification_level_labels.get(row.qualification_level, row.qualification_level or \'—\') }}\n                        </td>\n                        <td>\n                            {{ employment_labels.get(row.employment_type, row.employment_type or \'—\') }}\n                        </td>\n                        <td>\n                            {{ row.source_status_label or staff_status_labels.get(row.status_code, row.status_code or \'—\') }}\n                        </td>\n                    </tr>\n                    {% endfor %}\n                </tbody>\n            </table>\n        </div>\n        {% else %}\n        <div class="staff-empty">\n            Chưa tìm thấy danh sách nhân sự chi tiết của trường ở năm đang nhập\n            hoặc năm tham chiếu gần nhất. Các chỉ tiêu tổng hợp vẫn được giữ nguyên.\n        </div>\n        {% endif %}\n    </section>\n    <!-- === BAI_13B_6_V1_3_STAFF_TABLE_END === -->\n    {% endif %}\n'

FILES = [
    "app/routers/report_inputs.py",
    "app/templates/report_inputs/structured_school_form.html",
]


def read(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> list[dict]:
    BACKUP.mkdir(parents=True, exist_ok=False)
    manifest = []
    for rel in FILES:
        src = PROJECT / rel
        manifest.append({"path": rel, "existed": src.exists()})
        if src.exists():
            dst = BACKUP / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def restore(manifest: list[dict]) -> None:
    for item in reversed(manifest):
        target = PROJECT / item["path"]
        if item["existed"]:
            src = BACKUP / item["path"]
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)


def patch_router(text: str) -> str:
    if "BAI_13B_6_V1_3_MN_SCOPE_START" in text:
        return text

    if "BAI_13B_6_V1_2_NETWORK_DATA_START" not in text:
        raise RuntimeError(
            "Chưa tìm thấy nền Bài 13B-6 V1.2 FINAL trong report_inputs.py."
        )

    anchor = "\ndef _require_selected_school("
    if anchor not in text:
        raise RuntimeError("Không tìm thấy điểm chèn _mn_scope.")
    text = text.replace(
        anchor,
        MN_SCOPE_BLOCK + anchor,
        1,
    )

    gv_old = """def gv_report_input_page(
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    scope = _load_scope(db, request, school_year_id, commune_id, school_id)
"""
    gv_new = """def gv_report_input_page(
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    scope = _mn_scope(db, request, school_year_id, commune_id, school_id)
"""
    if gv_old not in text:
        raise RuntimeError("Không tìm thấy route MN-01-GV.")
    text = text.replace(gv_old, gv_new, 1)

    csvc_old = """def csvc_input_page(
    section: str,
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    if section not in CSVC_SECTIONS:
        return RedirectResponse(url="/csvc/co-so", status_code=303)
    scope = _load_scope(db, request, school_year_id, commune_id, school_id)
"""
    csvc_new = """def csvc_input_page(
    section: str,
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    if section not in CSVC_SECTIONS:
        return RedirectResponse(url="/csvc/co-so", status_code=303)
    scope = _mn_scope(db, request, school_year_id, commune_id, school_id)
"""
    if csvc_old not in text:
        raise RuntimeError("Không tìm thấy route MN-01-CSVC.")
    text = text.replace(csvc_old, csvc_new, 1)

    staff_anchor = "\ndef _structured_auto_values("
    if staff_anchor not in text:
        raise RuntimeError("Không tìm thấy điểm chèn danh sách nhân sự.")
    text = text.replace(
        staff_anchor,
        STAFF_DETAIL_BLOCK + staff_anchor,
        1,
    )

    old_page_part = """    network_reference_year = None
    if scope["selected_school_id"] and scope["selected_year_id"]:
        _network_data, network_reference_year = _structured_network_reference(
            db,
            school_id=int(scope["selected_school_id"]),
            level=catalog["level"],
            target_year_id=int(scope["selected_year_id"]),
        )

    effective_values, source_by_code = _structured_effective_values(
"""
    new_page_part = """    network_reference_year = None
    staff_detail_rows: list[StaffYearRecord] = []
    staff_detail_year = None

    if scope["selected_school_id"] and scope["selected_year_id"]:
        _network_data, network_reference_year = _structured_network_reference(
            db,
            school_id=int(scope["selected_school_id"]),
            level=catalog["level"],
            target_year_id=int(scope["selected_year_id"]),
        )

        if catalog["kind"] == "staff":
            staff_detail_rows, staff_detail_year = _structured_staff_detail_rows(
                db,
                school_id=int(scope["selected_school_id"]),
                target_year_id=int(scope["selected_year_id"]),
                level=catalog["level"],
            )

    effective_values, source_by_code = _structured_effective_values(
"""
    if old_page_part not in text:
        raise RuntimeError("Không tìm thấy phần context structured page.")
    text = text.replace(old_page_part, new_page_part, 1)

    old_context = """            "network_reference_year": network_reference_year,
        },
    )
"""
    new_context = """            "network_reference_year": network_reference_year,
            "staff_detail_rows": staff_detail_rows,
            "staff_detail_year": staff_detail_year,
            "staff_position_labels": {
                "CBQL": "CBQL",
                "GIAO_VIEN": "Giáo viên",
                "NHAN_VIEN": "Nhân viên",
            },
            "staff_status_labels": {
                "DANG_LAM_VIEC": "Đang làm việc",
                "CHUYEN_DI": "Chuyển đi",
                "NGHI_HUU": "Nghỉ hưu",
                "NGHI_VIEC": "Nghỉ việc",
                "TAM_NGHI": "Tạm nghỉ",
            },
            "employment_labels": EMPLOYMENT_LABELS,
            "qualification_level_labels": QUALIFICATION_LEVEL_LABELS,
        },
    )
"""
    if old_context not in text:
        raise RuntimeError("Không tìm thấy điểm thêm context nhân sự.")
    text = text.replace(old_context, new_context, 1)

    return text


def patch_template(text: str) -> str:
    if "BAI_13B_6_V1_3_STAFF_TABLE_START" in text:
        return text

    if "BÀI 13B-6" not in text:
        raise RuntimeError("Không tìm thấy template Bài 13B-6.")

    css_anchor = "        @media(max-width:1000px){"
    if css_anchor not in text:
        raise RuntimeError("Không tìm thấy điểm chèn CSS.")
    text = text.replace(
        css_anchor,
        STAFF_CSS + "\n" + css_anchor,
        1,
    )

    html_anchor = """    <form method="post" action="/bieu-nhap/{{ slug }}" id="structured-data-form">"""
    if html_anchor not in text:
        raise RuntimeError("Không tìm thấy điểm chèn bảng nhân sự.")
    text = text.replace(
        html_anchor,
        STAFF_HTML + "\n\n" + html_anchor,
        1,
    )

    return text


def verify_jinja() -> None:
    from jinja2 import Environment, FileSystemLoader
    env = Environment(
        loader=FileSystemLoader(str(PROJECT / "app" / "templates"))
    )
    env.get_template("report_inputs/structured_school_form.html")
    env.get_template("report_inputs/gv_mn01.html")
    env.get_template("report_inputs/csvc_mn01.html")


def main() -> int:
    print("=" * 96)
    print("BÀI 13B-6 V1.3")
    print("LỌC ĐÚNG TRƯỜNG MẦM NON + HIỆN TÊN NHÂN SỰ TIỂU HỌC/THCS")
    print("=" * 96)
    print("")
    print("SỬA 1:")
    print(" - MN-01-GV và MN-01-CSVC chỉ hiện trường/cơ sở Mầm non.")
    print(" - Loại các trường Tiểu học/THCS đã nhập từ dữ liệu mạng lưới.")
    print("")
    print("SỬA 2:")
    print(" - TH-01-GV và THCS-01-GV có thêm bảng danh sách nhân sự.")
    print(" - Hiện Họ tên, vị trí, chức vụ, môn dạy, trình độ, hình thức, trạng thái.")
    print(" - Nếu năm 2026-2027 chưa có hồ sơ chi tiết thì hiện danh sách tham chiếu 2025-2026.")
    print("")
    print("KHÔNG THAY ĐỔI:")
    print(" - Database và dữ liệu đã nhập.")
    print(" - Tổng hợp TH-01-GV / THCS-01-GV hiện có.")
    print(" - CSVC Tiểu học/THCS.")
    print(" - Báo cáo, điều tra hộ dân và giao diện điện thoại.")
    print("")

    for path in [ROUTER, TEMPLATE]:
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")

    router_before = read(ROUTER)
    template_before = read(TEMPLATE)

    if "BAI_13B_6_V1_2_NETWORK_DATA_START" not in router_before:
        raise RuntimeError(
            "Máy chưa ở trạng thái Bài 13B-6 V1.2 FINAL. Dừng cài để an toàn."
        )

    manifest = backup()

    try:
        ROUTER.write_text(
            patch_router(router_before),
            encoding="utf-8",
        )
        TEMPLATE.write_text(
            patch_template(template_before),
            encoding="utf-8",
        )

        subprocess.run(
            [sys.executable, "-m", "py_compile", str(ROUTER)],
            cwd=PROJECT,
            check=True,
        )
        verify_jinja()

        rcheck = read(ROUTER)
        tcheck = read(TEMPLATE)

        for marker in [
            "BAI_13B_6_V1_3_MN_SCOPE_START",
            "BAI_13B_6_V1_3_STAFF_DETAIL_START",
            "_mn_scope",
            "_structured_staff_detail_rows",
        ]:
            if marker not in rcheck:
                raise RuntimeError(f"Kiểm tra router không đạt: {marker}")

        for marker in [
            "BAI_13B_6_V1_3_STAFF_TABLE_START",
            "Danh sách nhân sự của trường",
            "row.staff_member.full_name",
        ]:
            if marker not in tcheck:
                raise RuntimeError(f"Kiểm tra template không đạt: {marker}")

        for cache in (PROJECT / "app").rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

        print("")
        print("CAI DAT BAI 13B-6 V1.3 THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        restore(manifest)
        print("")
        print("CÓ LỖI - ĐÃ KHÔI PHỤC 2 TỆP TỰ ĐỘNG.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
