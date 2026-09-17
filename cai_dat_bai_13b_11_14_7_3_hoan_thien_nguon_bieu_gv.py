from __future__ import annotations

import ast
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
ROUTER = APP / "routers" / "report_inputs.py"
TEMPLATE = APP / "templates" / "report_inputs" / "gv_mn01.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_11_14_7_3_{STAMP}"

DB_BACKUP = BACKUP / "data" / "phocap.db"
ROUTER_BACKUP = BACKUP / "app" / "routers" / "report_inputs.py"
TEMPLATE_BACKUP = BACKUP / "app" / "templates" / "report_inputs" / "gv_mn01.html"

TABLE = "staff_year_records"

REQUIRED_COLUMNS = (
    "employment_type",
    "teaching_age_group",
    "qualification_level",
    "qualification_standard",
    "professional_standard",
    "receives_policy",
)

ROUTER_MARKER = "# === BAI_13B_11_14_7_3_SOURCE_FIELDS_START ==="
TEMPLATE_MARKER = "{# === BAI_13B_11_14_7_3_SOURCE_FIELDS === #}"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig", errors="strict")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def sqlite_restore(source: Path, target: Path) -> None:
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def db_snapshot() -> dict:
    conn = sqlite3.connect(str(DB))
    try:
        cols = [
            str(row[1])
            for row in conn.execute(
                f'PRAGMA table_info("{TABLE}")'
            ).fetchall()
        ]
        if not cols:
            raise RuntimeError(f"Không tìm thấy bảng {TABLE}.")

        integrity = str(
            conn.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        count = int(
            conn.execute(
                f'SELECT COUNT(*) FROM "{TABLE}"'
            ).fetchone()[0]
        )

        nonnull = {}
        for col in REQUIRED_COLUMNS:
            if col not in cols:
                nonnull[col] = None
                continue

            sql = (
                f'SELECT COUNT(*) FROM "{TABLE}" '
                f'WHERE "{col}" IS NOT NULL'
            )
            nonnull[col] = int(conn.execute(sql).fetchone()[0])

        return {
            "columns": cols,
            "integrity": integrity,
            "fk": fk,
            "count": count,
            "nonnull": nonnull,
        }
    finally:
        conn.close()


def compile_python(path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if result.returncode != 0:
        raise RuntimeError(f"py_compile không đạt: {path}")


def patch_router(source: str) -> str:
    if ROUTER_MARKER in source:
        return source

    required_save_tokens = (
        'row.employment_type =',
        'row.teaching_age_group =',
        'row.qualification_level =',
        'row.qualification_standard =',
        'row.professional_standard =',
        'row.receives_policy =',
    )

    missing = [x for x in required_save_tokens if x not in source]
    if missing:
        raise RuntimeError(
            "POST MN-01-GV chưa có đủ save logic nền: "
            + ", ".join(missing)
        )

    anchor = '@router.get("/doi-ngu/nhap-mn-01-gv"'
    pos = source.find(anchor)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy route GET /doi-ngu/nhap-mn-01-gv."
        )

    block = '''
# === BAI_13B_11_14_7_3_SOURCE_FIELDS_START ===
# Bài 14.7.3 chỉ chuẩn hóa giao diện và nguồn nhập đã có.
# Không tạo field DB mới. Các tỷ lệ vẫn tự tính.
# === BAI_13B_11_14_7_3_SOURCE_FIELDS_END ===


'''
    source = source[:pos] + block + source[pos:]

    # Chuẩn hóa lưu receives_policy thành 3 trạng thái nếu source còn kiểu 0/1.
    old = (
        '        row.receives_policy = '
        'str(form.get(prefix + "policy") or "0") == "1"'
    )
    if old in source:
        new = '''        _b1473_policy_raw = str(
            form.get(prefix + "policy") or "CHUA_XAC_DINH"
        ).strip().upper()

        if _b1473_policy_raw in {"CO", "1", "TRUE"}:
            row.receives_policy = True
        elif _b1473_policy_raw in {"KHONG", "0", "FALSE"}:
            row.receives_policy = False
        else:
            row.receives_policy = None'''
        source = source.replace(old, new, 1)

    ast.parse(source)
    return source


def patch_template(source: str) -> str:
    if TEMPLATE_MARKER in source:
        return source

    if '<section class="panel" id="ra-soat">' not in source:
        raise RuntimeError(
            "Không tìm thấy phần Rà soát chỉ tiêu MN-01-GV."
        )

    source = source.replace(
        '<section class="panel" id="ra-soat">',
        TEMPLATE_MARKER + '\n            <section class="panel" id="ra-soat">',
        1,
    )

    # Chuẩn hóa nhãn cột.
    replacements = (
        ("<th>Hình thức</th>", "<th>Hình thức làm việc</th>"),
        ("<th>Trình độ</th>", "<th>Trình độ đào tạo</th>"),
        ("<th>Mức chuẩn</th>", "<th>Mức chuẩn đào tạo</th>"),
        ("<th>Hưởng CĐ/CS</th>", "<th>Hưởng chế độ/chính sách</th>"),
    )
    for old, new in replacements:
        source = source.replace(old, new, 1)

    # Thêm ghi chú tự tính, không nhập tay tỷ lệ.
    ra_soat_pos = source.find('<section class="panel" id="ra-soat">')
    h2_end = source.find("</h2>", ra_soat_pos)
    if h2_end > 0 and "Tỷ lệ GV/lớp không nhập tay" not in source:
        note = '''
                <div class="notice notice-ref" style="margin-bottom:16px;">
                    Các trường dưới đây là dữ liệu gốc phục vụ biểu MN-01-GV.
                    <strong>Tỷ lệ GV/lớp không nhập tay</strong>; hệ thống tự tính
                    từ số giáo viên và số nhóm/lớp lấy từ CSVC.
                </div>'''
        source = source[:h2_end + 5] + note + source[h2_end + 5:]

    # Nếu policy đang là checkbox, đổi sang select 3 trạng thái.
    checkbox_pattern = re.compile(
        r'(?is)<input\b[^>]*'
        r'name=["\']staff_\{\{\s*r\.id\s*\}\}_policy["\']'
        r'[^>]*>'
    )
    match = checkbox_pattern.search(source)
    if match:
        policy_select = '''<select
                                            class="mini-select"
                                            name="staff_{{ r.id }}_policy"
                                            {% if not can_edit %}disabled{% endif %}
                                        >
                                            <option value="CHUA_XAC_DINH"
                                                {% if r.receives_policy is none %}selected{% endif %}>
                                                Chưa xác định
                                            </option>
                                            <option value="CO"
                                                {% if r.receives_policy is sameas true %}selected{% endif %}>
                                                Có
                                            </option>
                                            <option value="KHONG"
                                                {% if r.receives_policy is sameas false %}selected{% endif %}>
                                                Không
                                            </option>
                                        </select>'''
        source = (
            source[:match.start()]
            + policy_select
            + source[match.end():]
        )

    # Nếu policy đã là select thì thay đúng select đó bằng bản 3 trạng thái.
    select_pattern = re.compile(
        r'(?is)<select\b[^>]*'
        r'name=["\']staff_\{\{\s*r\.id\s*\}\}_policy["\']'
        r'[^>]*>.*?</select>'
    )
    match = select_pattern.search(source)
    if match:
        policy_select = '''<select
                                            class="mini-select"
                                            name="staff_{{ r.id }}_policy"
                                            {% if not can_edit %}disabled{% endif %}
                                        >
                                            <option value="CHUA_XAC_DINH"
                                                {% if r.receives_policy is none %}selected{% endif %}>
                                                Chưa xác định
                                            </option>
                                            <option value="CO"
                                                {% if r.receives_policy is sameas true %}selected{% endif %}>
                                                Có
                                            </option>
                                            <option value="KHONG"
                                                {% if r.receives_policy is sameas false %}selected{% endif %}>
                                                Không
                                            </option>
                                        </select>'''
        source = (
            source[:match.start()]
            + policy_select
            + source[match.end():]
        )

    return source


def verify_router(source: str) -> None:
    ast.parse(source)
    for token in (
        ROUTER_MARKER,
        "row.employment_type",
        "row.teaching_age_group",
        "row.qualification_level",
        "row.qualification_standard",
        "row.professional_standard",
        "row.receives_policy",
    ):
        if token not in source:
            raise RuntimeError("Router sau cài thiếu: " + token)


def verify_template(source: str) -> None:
    from jinja2 import Environment
    Environment().parse(source)

    required = (
        TEMPLATE_MARKER,
        "Hình thức làm việc",
        "Dạy nhóm/lớp",
        "Trình độ đào tạo",
        "Mức chuẩn đào tạo",
        "Chuẩn nghề nghiệp",
        "Hưởng chế độ/chính sách",
        "Tỷ lệ GV/lớp không nhập tay",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Template sau cài thiếu: " + token)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 128)
    print(
        "BÀI 13B-11.14.7.3 - "
        "HOÀN THIỆN CÁC TRƯỜNG NGUỒN PHỤC VỤ BIỂU MN-01-GV"
    )
    print("=" * 128)
    print()
    print("TRƯỜNG NGUỒN:")
    print(" 1. Hình thức làm việc.")
    print(" 2. Dạy nhóm/lớp.")
    print(" 3. Trình độ đào tạo.")
    print(" 4. Mức chuẩn đào tạo.")
    print(" 5. Chuẩn nghề nghiệp.")
    print(" 6. Hưởng chế độ/chính sách.")
    print()
    print("NGUYÊN TẮC:")
    print(" - Không tạo menu/màn mới.")
    print(" - Không ALTER database.")
    print(" - Không sửa CSVC.")
    print(" - Giữ Dạy lớp ghép + CT 4 tuổi + CT 5 tuổi.")
    print(" - Tỷ lệ GV/lớp tự tính, không nhập tay.")
    print()

    for path in (DB, ROUTER, TEMPLATE):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    before = db_snapshot()

    print("integrity_check trước cài:", before["integrity"])
    print("foreign_key_check trước cài:", before["fk"], "lỗi")
    print("staff_year_records:", before["count"], "bản ghi")

    missing_columns = [
        col for col in REQUIRED_COLUMNS
        if col not in set(before["columns"])
    ]
    if missing_columns:
        raise RuntimeError(
            "Database thiếu cột nền: " + ", ".join(missing_columns)
        )

    if before["integrity"].lower() != "ok" or before["fk"] != 0:
        raise RuntimeError("Database không đạt kiểm tra an toàn trước cài.")

    router_before = read_text(ROUTER)
    template_before = read_text(TEMPLATE)

    if "/doi-ngu/nhap-mn-01-gv" not in router_before:
        raise RuntimeError("Không tìm thấy route MN-01-GV.")

    if "3. Rà soát chỉ tiêu MN-01-GV" not in template_before:
        raise RuntimeError("Không đúng template MN-01-GV hiện tại.")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER, ROUTER_BACKUP)
    backup_file(TEMPLATE, TEMPLATE_BACKUP)
    sqlite_backup(DB, DB_BACKUP)

    print("Backup:", BACKUP)

    try:
        router_after = patch_router(router_before)
        template_after = patch_template(template_before)

        verify_router(router_after)
        verify_template(template_after)

        write_text(ROUTER, router_after)
        write_text(TEMPLATE, template_after)

        compile_python(ROUTER)

        after = db_snapshot()

        if after["count"] != before["count"]:
            raise RuntimeError(
                "Số bản ghi staff_year_records bị thay đổi khi cài."
            )

        if after["nonnull"] != before["nonnull"]:
            raise RuntimeError(
                "Dữ liệu nguồn GV bị thay đổi trong lúc cài."
            )

        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check sau cài không OK.")

        if after["fk"] != 0:
            raise RuntimeError(
                f"foreign_key_check sau cài có {after['fk']} lỗi."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Hình thức làm việc: GIỮ NGUỒN HIỆN CÓ")
        print(" - Dạy nhóm/lớp: GIỮ NGUỒN HIỆN CÓ")
        print(" - Trình độ đào tạo: GIỮ NGUỒN HIỆN CÓ")
        print(" - Mức chuẩn đào tạo: GIỮ NGUỒN HIỆN CÓ")
        print(" - Chuẩn nghề nghiệp: GIỮ NGUỒN HIỆN CÓ")
        print(" - Chế độ/chính sách: Có/Không/Chưa xác định")
        print(" - Dạy lớp ghép + CT4T + CT5T: GIỮ NGUYÊN")
        print(" - Tỷ lệ GV/lớp: KHÔNG NHẬP TAY")
        print(" - Database: KHÔNG THAY ĐỔI DỮ LIỆU")
        print(" - py_compile: OK")
        print(" - Jinja: OK")
        print(" - integrity_check: OK")
        print(" - foreign_key_check: 0 lỗi")
        print()
        print("=" * 128)
        print("CÀI ĐẶT BÀI 13B-11.14.7.3 THÀNH CÔNG")
        print("=" * 128)
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC ROUTER/TEMPLATE/DATABASE...")

        try:
            shutil.copy2(ROUTER_BACKUP, ROUTER)
            print(" - Đã khôi phục router.")
        except Exception as exc:
            print(" - Lỗi khôi phục router:", exc)

        try:
            shutil.copy2(TEMPLATE_BACKUP, TEMPLATE)
            print(" - Đã khôi phục template.")
        except Exception as exc:
            print(" - Lỗi khôi phục template:", exc)

        try:
            sqlite_restore(DB_BACKUP, DB)
            print(" - Đã khôi phục database.")
        except Exception as exc:
            print(" - Lỗi khôi phục database:", exc)

        clear_cache()
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
