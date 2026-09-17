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
MODEL = APP / "survey_models.py"
ROUTER = APP / "routers" / "surveys.py"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
TRENDS = APP / "routers" / "survey_trends.py"
DB = PROJECT / "data" / "phocap.db"
TABLE = "survey_person_year_records"
FIELD = "attends_two_sessions_per_day"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_11_13_3_5_{STAMP}"
MODEL_START = "# === BAI_13B_11_13_3_5_TWO_SESSIONS_MODEL_START ==="
UI_START = "<!-- === BAI_13B_11_13_3_5_TWO_SESSIONS_UI_START === -->"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, path)


def sqlite_backup(source: Path, target: Path) -> None:
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()


def sqlite_restore(source: Path, target: Path) -> None:
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()


def db_state():
    conn = sqlite3.connect(str(DB))
    try:
        count = int(conn.execute(f'SELECT COUNT(*) FROM "{TABLE}"').fetchone()[0])
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{TABLE}")').fetchall()}
        return count, integrity, fk, cols
    finally:
        conn.close()


def add_db_column() -> None:
    conn = sqlite3.connect(str(DB))
    try:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{TABLE}")').fetchall()}
        if FIELD in cols:
            print(f" - DB đã có cột {FIELD}: giữ nguyên.")
            return
        conn.execute(f'ALTER TABLE "{TABLE}" ADD COLUMN "{FIELD}" BOOLEAN')
        conn.commit()
        print(f" - Đã tạo cột DB: {FIELD}")
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def assignment_name(node):
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def patch_model(text: str) -> str:
    if MODEL_START in text:
        return text
    tree = ast.parse(text)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SurveyPersonYearRecord"]
    if len(classes) != 1:
        raise RuntimeError(f"Phải có đúng 1 SurveyPersonYearRecord, hiện có {len(classes)}")
    cls = classes[0]
    stunted = None
    for node in cls.body:
        name = assignment_name(node)
        if name == FIELD:
            raise RuntimeError(f"Model đã có {FIELD} nhưng chưa có marker 13B-11.13.3.5")
        if name == "stunted":
            stunted = node
    if stunted is None:
        raise RuntimeError("Không tìm thấy field stunted trong model")
    lines = text.splitlines(keepends=True)
    block = (
        "\n    # === BAI_13B_11_13_3_5_TWO_SESSIONS_MODEL_START ===\n"
        "    # Tiêu chí 8: Học 2 buổi/ngày\n"
        "    attends_two_sessions_per_day: Mapped[bool | None] = mapped_column(\n"
        "        Boolean,\n"
        "        nullable=True,\n"
        "    )\n"
        "    # === BAI_13B_11_13_3_5_TWO_SESSIONS_MODEL_END ===\n"
    )
    lines.insert(int(stunted.end_lineno), block)
    patched = "".join(lines)
    ast.parse(patched)
    return patched


def patch_tuple(text: str, variable: str) -> str:
    tree = ast.parse(text)
    nodes = [n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign)) and assignment_name(n) == variable]
    if not nodes:
        return text
    if len(nodes) != 1:
        raise RuntimeError(f"Có {len(nodes)} khai báo {variable}")
    node = nodes[0]
    segment = ast.get_source_segment(text, node) or ""
    if FIELD in segment:
        return text
    if not isinstance(node.value, (ast.Tuple, ast.List)):
        raise RuntimeError(f"{variable} không phải tuple/list")
    lines = text.splitlines(keepends=True)
    indent = "    "
    if node.value.elts:
        line = lines[int(node.value.elts[0].lineno)-1]
        indent = line[:len(line)-len(line.lstrip())]
    lines.insert(int(node.end_lineno)-1, f'{indent}"{FIELD}",\n')
    patched = "".join(lines)
    ast.parse(patched)
    print(f" - Đã bổ sung vào {variable}")
    return patched


def top_function(tree, name):
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(nodes) != 1:
        raise RuntimeError(f"Phải có đúng 1 hàm {name}, hiện có {len(nodes)}")
    return nodes[0]


def patch_save_parameter(text: str) -> str:
    tree = ast.parse(text)
    fn = top_function(tree, "luu_theo_doi_nam_hoc")
    header_lines = text.splitlines(keepends=True)
    header_end = int(fn.body[0].lineno)-1
    header = "".join(header_lines[int(fn.lineno)-1:header_end])
    if re.search(rf"\b{FIELD}\s*:", header):
        return text
    for line_no in range(int(fn.lineno), header_end+1):
        line = header_lines[line_no-1]
        if re.match(r"\s*stunted\s*:", line):
            header_lines.insert(line_no, re.sub(r"\bstunted\b", FIELD, line, count=1))
            patched = "".join(header_lines)
            ast.parse(patched)
            print(" - Đã thêm tham số Form Học 2 buổi/ngày")
            return patched
    raise RuntimeError("Không tìm thấy tham số stunted trong route lưu")


def patch_tri_state(text: str) -> str:
    tree = ast.parse(text)
    fn = top_function(tree, "luu_theo_doi_nam_hoc")
    target = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "tri_state_inputs" for t in node.targets) and isinstance(node.value, ast.Dict):
            target = node.value; break
    if target is None:
        raise RuntimeError("Không tìm thấy tri_state_inputs")
    keys = {k.value for k in target.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    if FIELD in keys:
        return text
    stunted_key = next((k for k in target.keys if isinstance(k, ast.Constant) and k.value == "stunted"), None)
    if stunted_key is None:
        raise RuntimeError("tri_state_inputs không có stunted")
    lines = text.splitlines(keepends=True)
    source_line = lines[int(stunted_key.lineno)-1]
    indent = source_line[:len(source_line)-len(source_line.lstrip())]
    block = (
        f'{indent}"{FIELD}": (\n'
        f'{indent}    {FIELD},\n'
        f'{indent}    "Học 2 buổi/ngày",\n'
        f'{indent}),\n'
    )
    lines.insert(int(target.end_lineno)-1, block)
    patched = "".join(lines)
    ast.parse(patched)
    print(" - Đã thêm vào tri_state_inputs")
    return patched


def patch_fields_to_copy(text: str) -> str:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    inserts = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or assignment_name(node) != "fields_to_copy":
            continue
        if not isinstance(node.value, (ast.Tuple, ast.List)):
            continue
        values = [e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if "stunted" not in values or FIELD in values:
            continue
        first = node.value.elts[0]
        line = lines[int(first.lineno)-1]
        indent = line[:len(line)-len(line.lstrip())]
        inserts.append((int(node.value.end_lineno)-1, f'{indent}"{FIELD}",\n'))
    for idx, block in sorted(inserts, reverse=True):
        lines.insert(idx, block)
    patched = "".join(lines)
    ast.parse(patched)
    if inserts:
        print(f" - Đã thêm vào {len(inserts)} fields_to_copy")
    return patched


def patch_indicator_labels(text: str) -> str:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    inserts = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if "stunted" not in keys or FIELD in keys:
            continue
        values_text = " ".join(ast.get_source_segment(text, v) or "" for v in node.values)
        if "Suy dinh dưỡng" not in values_text and "thấp còi" not in values_text:
            continue
        key = next((k for k in node.keys if isinstance(k, ast.Constant) and k.value == "stunted"), None)
        if key is None:
            continue
        line = lines[int(key.lineno)-1]
        indent = line[:len(line)-len(line.lstrip())]
        inserts.append((int(node.end_lineno)-1, f'{indent}"{FIELD}": "Học 2 buổi/ngày",\n'))
    for idx, block in sorted(inserts, reverse=True):
        lines.insert(idx, block)
    patched = "".join(lines)
    ast.parse(patched)
    return patched


def find_matching_div_end(text: str, start: int) -> int:
    token = re.compile(r"<div\b[^>]*>|</div>", re.I)
    depth = 0
    for match in token.finditer(text, start):
        if match.group(0).lower().startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return match.end()
    raise RuntimeError("Không tìm thấy </div> khớp")


def find_stunted_card(text: str):
    pos_field = text.find('name="stunted"')
    if pos_field < 0:
        raise RuntimeError('Không tìm thấy name="stunted"')
    pos = text.rfind("<div", 0, pos_field)
    while pos >= 0:
        opening_end = text.find(">", pos)
        opening = text[pos:opening_end+1]
        if "indicator-item" in opening:
            end = find_matching_div_end(text, pos)
            if pos < pos_field < end:
                return pos, end
        pos = text.rfind("<div", 0, pos)
    raise RuntimeError("Không xác định được card stunted")


def patch_template(text: str) -> str:
    if UI_START in text:
        return text
    if f'name="{FIELD}"' in text:
        raise RuntimeError(f"Template đã có {FIELD} nhưng chưa có marker")
    _, end = find_stunted_card(text)
    block = r'''
                            <!-- === BAI_13B_11_13_3_5_TWO_SESSIONS_UI_START === -->
                            <div class="indicator-item">
                                <label for="attends_two_sessions_per_day">
                                    8. Học 2 buổi/ngày
                                </label>
                                <select
                                    id="attends_two_sessions_per_day"
                                    name="attends_two_sessions_per_day"
                                    class="form-control"
                                >
                                    <option value="" {% if not selected_record or selected_record.attends_two_sessions_per_day is none %}selected{% endif %}>-- Chưa xác định --</option>
                                    <option value="1" {% if selected_record and selected_record.attends_two_sessions_per_day is sameas true %}selected{% endif %}>Có</option>
                                    <option value="0" {% if selected_record and selected_record.attends_two_sessions_per_day is sameas false %}selected{% endif %}>Không</option>
                                </select>
                            </div>
                            <!-- === BAI_13B_11_13_3_5_TWO_SESSIONS_UI_END === -->'''
    patched = text[:end] + "\n" + block + text[end:]
    from jinja2 import Environment
    Environment().parse(patched)
    return patched


def compile_py(path: Path) -> None:
    result = subprocess.run([sys.executable, "-m", "py_compile", str(path)], cwd=PROJECT, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if result.returncode != 0:
        raise RuntimeError(f"py_compile không đạt: {path}")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def verify(count_before: int) -> None:
    model = read_text(MODEL)
    router = read_text(ROUTER)
    template = read_text(TEMPLATE)
    if FIELD not in model or MODEL_START not in model:
        raise RuntimeError("Model chưa có field mới")
    if FIELD not in router or '"Học 2 buổi/ngày"' not in router:
        raise RuntimeError("Router chưa lưu field mới")
    if UI_START not in template or f'name="{FIELD}"' not in template or "8. Học 2 buổi/ngày" not in template:
        raise RuntimeError("Template chưa có chỉ báo mới")
    if "B131133_MN_FIELDS" in router:
        tree = ast.parse(router)
        node = next((n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign)) and assignment_name(n) == "B131133_MN_FIELDS"), None)
        if node is None or FIELD not in (ast.get_source_segment(router, node) or ""):
            raise RuntimeError("B131133_MN_FIELDS chưa tính chỉ báo mới")
    from jinja2 import Environment
    Environment().parse(template)
    compile_py(MODEL); compile_py(ROUTER)
    if TRENDS.exists():
        compile_py(TRENDS)
    count, integrity, fk, cols = db_state()
    if FIELD not in cols:
        raise RuntimeError("Database chưa có cột mới")
    if count != count_before:
        raise RuntimeError(f"Số bản ghi thay đổi: {count_before} -> {count}")
    if integrity.lower() != "ok":
        raise RuntimeError(f"integrity_check: {integrity}")
    if fk != 0:
        raise RuntimeError(f"foreign_key_check có {fk} lỗi")


def main() -> int:
    print("=" * 124)
    print("BÀI 13B-11.13.3.5 - BỔ SUNG CHỈ SỐ MẦM NON: HỌC 2 BUỔI/NGÀY")
    print("=" * 124)
    print()
    print("BỔ SUNG:")
    print(" - 8. Học 2 buổi/ngày")
    print(" - Chưa xác định / Có / Không")
    print(" - Lưu theo từng đối tượng, từng năm học")
    print(" - Tính vào điều kiện hoàn thành thông tin Mầm non")
    print()
    print("SAU KHI CÀI:")
    print(" - 1 chỉ tiêu Hoàn thành Chương trình GDMN theo độ tuổi")
    print(" - 8 chỉ báo Mầm non đánh số 1 -> 8")
    print(" - Logic tiến độ Mầm non có tổng 9 trường bắt buộc")
    print()
    print("AN TOÀN:")
    print(" - Backup model/router/template/database")
    print(" - Chỉ ADD COLUMN nullable, không sửa dữ liệu cũ")
    print(" - Không ảnh hưởng TH, THCS, XMC")
    print(" - Có lỗi tự rollback")
    print()

    for path in (MODEL, ROUTER, TEMPLATE, DB):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    count_before, integrity, fk, _ = db_state()
    if integrity.lower() != "ok" or fk != 0:
        raise RuntimeError("Database không đạt kiểm tra trước khi cài")

    BACKUP.mkdir(parents=True, exist_ok=False)
    for path in (MODEL, ROUTER, TEMPLATE, TRENDS):
        backup_file(path)
    db_backup = BACKUP / "phocap.db"
    sqlite_backup(DB, db_backup)
    print("Backup:", BACKUP)
    print("survey_person_year_records trước cài:", count_before)

    try:
        add_db_column()

        model_text = patch_model(read_text(MODEL))
        write_text(MODEL, model_text)

        router_text = read_text(ROUTER)
        router_text = patch_tuple(router_text, "BOOLEAN_YEAR_FIELDS")
        router_text = patch_tuple(router_text, "B131133_MN_FIELDS")
        router_text = patch_save_parameter(router_text)
        router_text = patch_tri_state(router_text)
        router_text = patch_fields_to_copy(router_text)
        router_text = patch_indicator_labels(router_text)
        write_text(ROUTER, router_text)

        write_text(TEMPLATE, patch_template(read_text(TEMPLATE)))

        if TRENDS.exists():
            write_text(TRENDS, patch_indicator_labels(read_text(TRENDS)))

        verify(count_before)
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Database field mới: OK")
        print(" - Model: OK")
        print(" - Route lưu: OK")
        print(" - Logic tiến độ Mầm non: OK")
        print(" - Giao diện 8. Học 2 buổi/ngày: OK")
        print(" - py_compile/Jinja: OK")
        print(" - integrity_check: OK")
        print(" - foreign_key_check: 0 lỗi")
        print(" - Dữ liệu cũ giữ nguyên:", count_before, "bản ghi")
        print()
        print("CÀI ĐẶT BÀI 13B-11.13.3.5 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE VÀ DATABASE...")
        for path in (MODEL, ROUTER, TEMPLATE, TRENDS):
            try:
                restore_file(path)
            except Exception as exc:
                print(" - Lỗi khôi phục", path, exc)
        try:
            sqlite_restore(db_backup, DB)
            print(" - Đã khôi phục database.")
        except Exception as exc:
            print(" - Lỗi khôi phục database:", exc)
        clear_cache()
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
