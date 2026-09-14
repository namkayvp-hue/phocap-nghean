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


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

DB = PROJECT / "data" / "phocap.db"
MODEL = PROJECT / "app" / "staff_models.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_14_7_1_1_{STAMP}"
)

DB_BACKUP = BACKUP / "data" / "phocap.db"
MODEL_BACKUP = BACKUP / "app" / "staff_models.py"

TABLE = "staff_year_records"

NEW_COLUMNS = (
    "teaches_multigrade",
    "uses_multigrade_program_4yo",
    "uses_multigrade_program_5yo",
)

MODEL_MARKER_START = (
    "# === BAI_13B_11_14_7_1_1_MULTIGRADE_FIELDS_START ==="
)

MODEL_MARKER_END = (
    "# === BAI_13B_11_14_7_1_1_MULTIGRADE_FIELDS_END ==="
)


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(path: Path, text_value: str) -> None:
    path.write_text(
        text_value,
        encoding="utf-8",
    )


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
        is not None
    )


def table_columns(
    conn: sqlite3.Connection,
    table: str,
) -> list[str]:
    return [
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    ]


def table_count(
    conn: sqlite3.Connection,
    table: str,
) -> int:
    return int(
        conn.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    )


def db_health(
    conn: sqlite3.Connection,
) -> tuple[str, int]:
    integrity = str(
        conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    fk = len(
        conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    )

    return integrity, fk


def snapshot_db() -> dict:
    conn = sqlite3.connect(str(DB))

    try:
        if not table_exists(conn, TABLE):
            raise RuntimeError(
                f"Không có bảng {TABLE}"
            )

        integrity, fk = db_health(conn)

        return {
            "integrity": integrity,
            "fk": fk,
            "columns": table_columns(
                conn,
                TABLE,
            ),
            "count": table_count(
                conn,
                TABLE,
            ),
        }

    finally:
        conn.close()


def add_db_columns() -> None:
    conn = sqlite3.connect(str(DB))

    try:
        conn.execute(
            "PRAGMA foreign_keys = ON"
        )

        current = set(
            table_columns(
                conn,
                TABLE,
            )
        )

        for column in NEW_COLUMNS:
            if column in current:
                continue

            sql = (
                f'ALTER TABLE "{TABLE}" '
                f'ADD COLUMN "{column}" BOOLEAN'
            )

            conn.execute(sql)

        conn.commit()

    finally:
        conn.close()


def find_staff_year_class(
    source: str,
):
    tree = ast.parse(source)

    candidates = []

    for node in tree.body:
        if not isinstance(
            node,
            ast.ClassDef,
        ):
            continue

        table_name = None

        for stmt in node.body:
            if not isinstance(
                stmt,
                (
                    ast.Assign,
                    ast.AnnAssign,
                ),
            ):
                continue

            targets = (
                stmt.targets
                if isinstance(
                    stmt,
                    ast.Assign,
                )
                else [stmt.target]
            )

            for target in targets:
                if (
                    isinstance(
                        target,
                        ast.Name,
                    )
                    and target.id
                    == "__tablename__"
                ):
                    value = getattr(
                        stmt,
                        "value",
                        None,
                    )

                    if (
                        isinstance(
                            value,
                            ast.Constant,
                        )
                        and isinstance(
                            value.value,
                            str,
                        )
                    ):
                        table_name = (
                            value.value
                        )

        if table_name == TABLE:
            candidates.append(
                node
            )

    if len(candidates) != 1:
        raise RuntimeError(
            "Phải tìm thấy đúng 1 model có "
            f'__tablename__ = "{TABLE}"; '
            f"hiện có {len(candidates)}."
        )

    return candidates[0]


def find_clone_line(
    class_text: str,
) -> tuple[str, str]:
    preferred = (
        "receives_policy",
        "professional_standard",
        "qualification_standard",
        "is_active",
    )

    lines = class_text.splitlines()

    for field in preferred:
        pattern = re.compile(
            rf"^(?P<indent>\s*)"
            rf"(?P<name>{re.escape(field)})"
            rf"(?P<rest>\s*(?::[^=]+)?=\s*.+)$"
        )

        for line in lines:
            match = pattern.match(
                line
            )

            if not match:
                continue

            rest = match.group(
                "rest"
            )

            if "Boolean" not in rest:
                continue

            return (
                match.group(
                    "indent"
                ),
                rest,
            )

    raise RuntimeError(
        "Không tìm thấy field Boolean "
        "trong StaffYearRecord để clone style model."
    )


def patch_model(
    source: str,
) -> str:
    if (
        "teaches_multigrade"
        in source
        and "uses_multigrade_program_4yo"
        in source
        and "uses_multigrade_program_5yo"
        in source
    ):
        return source

    node = find_staff_year_class(
        source
    )

    lines = source.splitlines(
        keepends=True
    )

    start_index = (
        int(node.lineno) - 1
    )

    end_index = int(
        node.end_lineno
    )

    class_text = "".join(
        lines[
            start_index:
            end_index
        ]
    )

    indent, rest = find_clone_line(
        class_text
    )

    if (
        "uses_multigrade_program_4yo"
        in class_text
        or "uses_multigrade_program_5yo"
        in class_text
    ):
        raise RuntimeError(
            "Model đã có một phần field chương trình lớp ghép "
            "4/5 tuổi nhưng chưa đủ; dừng để tránh chèn trùng."
        )

    insert_after = None

    for index in range(
        start_index,
        end_index,
    ):
        if re.match(
            r"^\s*receives_policy(?:\s*:|\s*=)",
            lines[index],
        ):
            insert_after = index
            break

    if insert_after is None:
        for index in range(
            start_index,
            end_index,
        ):
            if re.match(
                r"^\s*professional_standard(?:\s*:|\s*=)",
                lines[index],
            ):
                insert_after = index
                break

    if insert_after is None:
        raise RuntimeError(
            "Không xác định được vị trí an toàn "
            "để chèn field lớp ghép."
        )

    block_lines = [
        f"{indent}{MODEL_MARKER_START}\n",
    ]

    if "teaches_multigrade" not in class_text:
        block_lines.append(
            f"{indent}teaches_multigrade{rest}\n"
        )

    block_lines.extend(
        [
            f"{indent}uses_multigrade_program_4yo{rest}\n",
            f"{indent}uses_multigrade_program_5yo{rest}\n",
            f"{indent}{MODEL_MARKER_END}\n",
        ]
    )

    block = "".join(block_lines)

    lines.insert(
        insert_after + 1,
        block,
    )

    patched = "".join(
        lines
    )

    ast.parse(
        patched
    )

    return patched


def compile_model() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(MODEL),
        ],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(
            result.stdout.rstrip()
        )

    if result.stderr:
        print(
            result.stderr.rstrip()
        )

    if result.returncode != 0:
        raise RuntimeError(
            "py_compile staff_models.py không đạt."
        )


def verify_model_source() -> None:
    source = read_text(
        MODEL
    )

    for item in (
        "teaches_multigrade",
        "uses_multigrade_program_4yo",
        "uses_multigrade_program_5yo",
        MODEL_MARKER_START,
        MODEL_MARKER_END,
    ):
        if item not in source:
            raise RuntimeError(
                "Model sau cài thiếu: "
                + item
            )

    find_staff_year_class(
        source
    )

    compile_model()


def clear_cache() -> None:
    for cache in (
        PROJECT
        / "app"
    ).rglob(
        "__pycache__"
    ):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    print("=" * 124)
    print(
        "BÀI 13B-11.14.7.1 - "
        "BỔ SUNG 2 TRƯỜNG GV DẠY LỚP GHÉP / "
        "CHƯƠNG TRÌNH LỚP GHÉP"
    )
    print("=" * 124)
    print()
    print("KẾT QUẢ KHẢO SÁT 14.7.0:")
    print(
        " - staff_year_records đã có "
        "position_group/position_title."
    )
    print(
        " - Đã có employment_type, "
        "qualification_level, qualification_standard."
    )
    print(
        " - Đã có professional_standard, "
        "staff_evaluation, status_code."
    )
    print(
        " - Đã có receives_policy và "
        "staff_policy_year_records."
    )
    print()
    print("CHỈ BỔ SUNG PHẦN THỰC SỰ THIẾU:")
    print(
        " 1. teaches_multigrade: "
        "GV có dạy lớp ghép hay không."
    )
    print(
        " 2. uses_multigrade_program_4yo: "
        "Có thực hiện chương trình lớp ghép 4 tuổi hay không."
    )
    print(
        " 3. uses_multigrade_program_5yo: "
        "Có thực hiện chương trình lớp ghép 5 tuổi hay không."
    )
    print()
    print("KIỂU DỮ LIỆU:")
    print(
        " - BOOLEAN nullable: "
        "NULL = Chưa xác định; 1 = Có; 0 = Không."
    )
    print()
    print(
        "LƯU Ý TƯƠNG THÍCH:"
    )
    print(
        " - Nếu Bài 14.7.1 cũ đã từng chạy, cột "
        "uses_multigrade_program cũ sẽ được giữ nguyên nhưng "
        "không dùng cho nghiệp vụ mới."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Không tạo lại các field GV đã có."
    )
    print(
        " - Không UPDATE dữ liệu 63.787 bản ghi hiện hữu."
    )
    print(
        " - Chỉ ALTER ADD COLUMN khi field chưa tồn tại."
    )
    print(
        " - Backup database + staff_models.py."
    )
    print(
        " - py_compile + integrity + foreign key."
    )
    print(
        " - Có lỗi tự rollback source và database."
    )
    print()

    for path in (
        DB,
        MODEL,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    before = snapshot_db()

    print(
        "integrity_check trước cài:",
        before["integrity"],
    )

    print(
        "foreign_key_check trước cài:",
        before["fk"],
        "lỗi",
    )

    print(
        "staff_year_records trước cài:",
        before["count"],
        "bản ghi",
    )

    if (
        before["integrity"].lower()
        != "ok"
        or before["fk"] != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra trước cài."
        )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    MODEL_BACKUP.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        MODEL,
        MODEL_BACKUP,
    )

    sqlite_backup(
        DB,
        DB_BACKUP,
    )

    print(
        "Backup:",
        BACKUP,
    )

    try:
        original_model = read_text(
            MODEL
        )

        patched_model = patch_model(
            original_model
        )

        write_text(
            MODEL,
            patched_model,
        )

        verify_model_source()

        add_db_columns()

        after = snapshot_db()

        missing = [
            column
            for column in NEW_COLUMNS
            if column
            not in set(
                after["columns"]
            )
        ]

        if missing:
            raise RuntimeError(
                "Database sau cài thiếu cột: "
                + ", ".join(
                    missing
                )
            )

        if (
            after["count"]
            != before["count"]
        ):
            raise RuntimeError(
                "Số bản ghi staff_year_records "
                "bị thay đổi."
            )

        if (
            after["integrity"].lower()
            != "ok"
        ):
            raise RuntimeError(
                "integrity_check sau cài không OK."
            )

        if after["fk"] != 0:
            raise RuntimeError(
                "foreign_key_check sau cài "
                f"có {after['fk']} lỗi."
            )

        conn = sqlite3.connect(
            str(DB)
        )

        try:
            nonnull = {}

            for column in NEW_COLUMNS:
                nonnull[column] = int(
                    conn.execute(
                        f'SELECT COUNT(*) '
                        f'FROM "{TABLE}" '
                        f'WHERE "{column}" IS NOT NULL'
                    ).fetchone()[0]
                )

        finally:
            conn.close()

        if any(
            value != 0
            for value in nonnull.values()
        ):
            raise RuntimeError(
                "Bộ cài không được tự điền dữ liệu "
                "cho các field lớp ghép mới."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - teaches_multigrade: ĐÃ CÓ"
        )
        print(
            " - uses_multigrade_program_4yo: ĐÃ CÓ"
        )
        print(
            " - uses_multigrade_program_5yo: ĐÃ CÓ"
        )
        print(
            " - Dữ liệu cũ: NULL / Chưa xác định"
        )
        print(
            " - staff_year_records:",
            after["count"],
            "bản ghi - GIỮ NGUYÊN",
        )
        print(
            " - Không tạo trùng field GV cũ: OK"
        )
        print(
            " - staff_models.py: py_compile OK"
        )
        print(
            " - integrity_check: OK"
        )
        print(
            " - foreign_key_check: 0 lỗi"
        )
        print()
        print("=" * 124)
        print(
            "CÀI ĐẶT BÀI 13B-11.14.7.1.1 THÀNH CÔNG"
        )
        print("=" * 124)
        print()
        print("BƯỚC TIẾP THEO:")
        print(
            " - 14.7.2: nối 3 trường lớp ghép + "
            "các trường GV hiện có vào giao diện nhập Đội ngũ."
        )
        print(
            " - 14.7.3: giao diện chi tiết "
            "nhiều chế độ/chính sách của GV."
        )

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC "
            "SOURCE VÀ DATABASE..."
        )

        try:
            shutil.copy2(
                MODEL_BACKUP,
                MODEL,
            )

            print(
                " - Đã khôi phục staff_models.py."
            )

        except Exception as exc:
            print(
                " - Lỗi khôi phục model:",
                exc,
            )

        try:
            sqlite_restore(
                DB_BACKUP,
                DB,
            )

            print(
                " - Đã khôi phục database."
            )

        except Exception as exc:
            print(
                " - Lỗi khôi phục database:",
                exc,
            )

        clear_cache()

        print(
            "Backup:",
            BACKUP,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
