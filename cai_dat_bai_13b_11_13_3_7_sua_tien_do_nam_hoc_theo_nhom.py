from __future__ import annotations

import ast
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
ROUTER = APP / "routers" / "surveys.py"
TEMPLATE = APP / "templates" / "surveys" / "year_overview.html"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_11_13_3_7_{STAMP}"

MARK_START = "# === BAI_13B_11_13_3_7_YEAR_OVERVIEW_DYNAMIC_START ==="
MARK_END = "# === BAI_13B_11_13_3_7_YEAR_OVERVIEW_DYNAMIC_END ==="

OLD_BLOCK = '''        current_answered = (
            sum(
                value is not None
                for value in (
                    current_record.completed_preschool_5,
                    current_record.attends_required_days,
                    current_record.attends_regularly,
                    current_record.prepared_vietnamese,
                    current_record.weight_monitored,
                    current_record.underweight,
                    current_record.height_monitored,
                    current_record.stunted,
                )
            )
            if current_record
            else 0
        )
'''

NEW_BLOCK = '''        # === BAI_13B_11_13_3_7_YEAR_OVERVIEW_DYNAMIC_START ===
        current_progress = b131133_tien_do_nam_hoc(
            person=person,
            record=current_record,
            school_year=survey_form.survey_batch.school_year,
        )
        current_answered = int(
            current_progress["answered"]
        )
        current_total = int(
            current_progress["total"]
        )
        # === BAI_13B_11_13_3_7_YEAR_OVERVIEW_DYNAMIC_END ===
'''


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def db_check() -> tuple[str, int, int]:
    conn = sqlite3.connect(str(DB))
    try:
        integrity = str(
            conn.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_count = len(
            conn.execute("PRAGMA foreign_key_check").fetchall()
        )
        count = int(
            conn.execute(
                "SELECT COUNT(*) FROM survey_person_year_records"
            ).fetchone()[0]
        )
        return integrity, fk_count, count
    finally:
        conn.close()


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


def extract_function(text: str, name: str) -> tuple[int, int]:
    tree = ast.parse(text)

    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm {name}; hiện có {len(matches)}."
        )

    node = matches[0]
    lines = text.splitlines(keepends=True)

    start = sum(
        len(line)
        for line in lines[: int(node.lineno) - 1]
    )
    end = sum(
        len(line)
        for line in lines[: int(node.end_lineno)]
    )

    return start, end


def patch_router(text: str) -> str:
    if "def b131133_tien_do_nam_hoc" not in text:
        raise RuntimeError(
            "Không thấy helper động b131133_tien_do_nam_hoc."
        )

    start, end = extract_function(
        text,
        "tong_quan_theo_doi_nam_hoc",
    )

    fn = text[start:end]

    if MARK_START not in fn:
        if OLD_BLOCK not in fn:
            raise RuntimeError(
                "Không tìm thấy khối current_answered cố định cũ "
                "trong tong_quan_theo_doi_nam_hoc."
            )

        fn = fn.replace(
            OLD_BLOCK,
            NEW_BLOCK,
            1,
        )

    old_total = '"current_year_total": len(BOOLEAN_YEAR_FIELDS),'

    if old_total in fn:
        fn = fn.replace(
            old_total,
            '"current_year_total": current_total,',
            1,
        )

    if '"current_year_total": current_total,' not in fn:
        raise RuntimeError(
            "Chưa thay được current_year_total sang tổng động."
        )

    patched = text[:start] + fn + text[end:]

    ast.parse(patched)
    return patched


def patch_template(text: str) -> str:
    text = text.replace(
        "Chỉ báo đã nhập",
        "Thông tin đã nhập",
    )
    return text


def verify_router(text: str) -> None:
    start, end = extract_function(
        text,
        "tong_quan_theo_doi_nam_hoc",
    )
    fn = text[start:end]

    required = [
        MARK_START,
        MARK_END,
        "b131133_tien_do_nam_hoc(",
        'current_progress["answered"]',
        'current_progress["total"]',
        '"current_year_total": current_total,',
    ]

    for item in required:
        if item not in fn:
            raise RuntimeError(
                "Router thiếu sau cài: " + item
            )

    if (
        '"current_year_total": len(BOOLEAN_YEAR_FIELDS),'
        in fn
    ):
        raise RuntimeError(
            "Vẫn còn tổng cố định BOOLEAN_YEAR_FIELDS "
            "trong màn tổng quan năm học."
        )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(ROUTER),
        ],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())

    if result.returncode != 0:
        raise RuntimeError(
            "py_compile surveys.py không đạt."
        )


def verify_template(text: str) -> None:
    from jinja2 import Environment

    Environment().parse(text)

    if "Thông tin đã nhập" not in text:
        raise RuntimeError(
            "year_overview.html chưa đổi nhãn "
            "sang 'Thông tin đã nhập'."
        )


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 122)
    print(
        "BÀI 13B-11.13.3.7 - "
        "SỬA TIẾN ĐỘ 7/9 Ở THEO DÕI THÔNG TIN TỪNG NĂM HỌC"
    )
    print("=" * 122)
    print()
    print("LỖI:")
    print(
        " - Màn tổng quan năm học vẫn đếm các trường Mầm non cố định."
    )
    print(
        " - Vì vậy MN/TH/THCS đều hiện cùng dạng 7/9."
    )
    print()
    print("SỬA:")
    print(
        " - Dùng b131133_tien_do_nam_hoc cho từng đối tượng."
    )
    print(
        " - Tổng cần nhập thay đổi đúng theo MN/TH/THCS/XMC."
    )
    print(
        " - XMC chỉ cộng chi tiết XMC khi XMC = Có."
    )
    print(
        " - Đổi nhãn 'Chỉ báo đã nhập' thành 'Thông tin đã nhập'."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Chỉ sửa surveys.py + year_overview.html."
    )
    print(" - Không sửa database.")
    print(" - Có backup + rollback nếu lỗi.")
    print()

    for path in (ROUTER, TEMPLATE, DB):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    integrity_before, fk_before, count_before = db_check()

    if integrity_before.lower() != "ok" or fk_before != 0:
        raise RuntimeError(
            "Database không đạt kiểm tra trước khi cài."
        )

    BACKUP.mkdir(parents=True, exist_ok=False)

    backup_file(ROUTER)
    backup_file(TEMPLATE)

    print("Backup:", BACKUP)
    print(
        "survey_person_year_records:",
        count_before,
        "bản ghi",
    )

    try:
        router_text = patch_router(
            read_text(ROUTER)
        )
        template_text = patch_template(
            read_text(TEMPLATE)
        )

        ast.parse(router_text)

        from jinja2 import Environment
        Environment().parse(template_text)

        write_text(ROUTER, router_text)
        write_text(TEMPLATE, template_text)

        verify_router(read_text(ROUTER))
        verify_template(read_text(TEMPLATE))

        integrity_after, fk_after, count_after = db_check()

        if integrity_after.lower() != "ok":
            raise RuntimeError(
                "integrity_check sau cài không đạt."
            )
        if fk_after != 0:
            raise RuntimeError(
                f"foreign_key_check có {fk_after} lỗi."
            )
        if count_after != count_before:
            raise RuntimeError(
                "Số bản ghi năm học bị thay đổi."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Tổng quan năm học dùng tiến độ động: OK"
        )
        print(
            " - Không còn current_year_total cố định: OK"
        )
        print(
            " - Nhãn 'Thông tin đã nhập': OK"
        )
        print(" - py_compile: OK")
        print(" - Jinja parse: OK")
        print(" - integrity_check: OK")
        print(" - foreign_key_check: 0 lỗi")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print(
            "CÀI ĐẶT BÀI "
            "13B-11.13.3.7 THÀNH CÔNG"
        )

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC SOURCE..."
        )

        restore_file(ROUTER)
        restore_file(TEMPLATE)
        clear_cache()

        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup:", BACKUP)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
