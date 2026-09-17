from __future__ import annotations

import ast
import importlib
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
DB_PATH = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_11_13_1_{STAMP}"

TABLE = "survey_person_year_records"

NEW_COLUMNS = [
    (
        "is_literacy_target",
        "BOOLEAN",
        None,
        "Đối tượng điều tra Xóa mù chữ: NULL=Chưa xác định, 1=Có, 0=Không",
    ),
    (
        "literacy_status",
        "VARCHAR(30)",
        "'CHUA_XAC_DINH'",
        "Tình trạng XMC: CHUA_XAC_DINH / KHONG_THUOC_DIEN / THEO_DOI_XMC",
    ),
    (
        "completed_grade_3",
        "BOOLEAN",
        None,
        "Hoàn thành lớp 3: NULL=Chưa xác định, 1=Có, 0=Không",
    ),
    (
        "completed_grade_5",
        "BOOLEAN",
        None,
        "Hoàn thành lớp 5: NULL=Chưa xác định, 1=Có, 0=Không",
    ),
    (
        "completed_primary_program",
        "BOOLEAN",
        None,
        "Hoàn thành chương trình Tiểu học",
    ),
    (
        "completed_lower_secondary_program",
        "BOOLEAN",
        None,
        "Hoàn thành chương trình THCS",
    ),
    (
        "post_lower_secondary_path",
        "VARCHAR(30)",
        "'CHUA_XAC_DINH'",
        "Hướng học sau THCS: CHUA_XAC_DINH / THPT / GDTX / GDNN / KHONG_HOC",
    ),
]

MODEL_FIELDS = """    # === BAI_13B_11_13_1_XMC_TH_THCS_FIELDS_START ===
    is_literacy_target: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    literacy_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="CHUA_XAC_DINH",
        server_default="CHUA_XAC_DINH",
    )
    completed_grade_3: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    completed_grade_5: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    completed_primary_program: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    completed_lower_secondary_program: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    post_lower_secondary_path: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="CHUA_XAC_DINH",
        server_default="CHUA_XAC_DINH",
    )
    # === BAI_13B_11_13_1_XMC_TH_THCS_FIELDS_END ===
"""

MARK_START = "# === BAI_13B_11_13_1_XMC_TH_THCS_FIELDS_START ==="
MARK_END = "# === BAI_13B_11_13_1_XMC_TH_THCS_FIELDS_END ==="


def say(text: str = "") -> None:
    print(text)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def sqlite_restore(source_backup: Path, target_db: Path) -> None:
    src = sqlite3.connect(str(source_backup))
    dst = sqlite3.connect(str(target_db))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def db_columns(db_path: Path) -> dict[str, tuple]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            f'PRAGMA table_info("{TABLE}")'
        ).fetchall()
        return {str(row[1]): row for row in rows}
    finally:
        conn.close()


def db_count(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return int(
            conn.execute(
                f'SELECT COUNT(*) FROM "{TABLE}"'
            ).fetchone()[0]
        )
    finally:
        conn.close()


def db_integrity(db_path: Path) -> tuple[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        integrity = str(
            conn.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_total = len(
            conn.execute("PRAGMA foreign_key_check").fetchall()
        )
        return integrity, fk_total
    finally:
        conn.close()


def locate_model_source() -> tuple[Path, ast.ClassDef]:
    candidates: list[tuple[Path, ast.ClassDef]] = []

    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue

        try:
            text = read_text(path)
            tree = ast.parse(text)
        except Exception:
            continue

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            if node.name == "SurveyPersonYearRecord":
                candidates.append((path, node))
                continue

            class_text = ast.get_source_segment(text, node) or ""
            if (
                "survey_person_year_records" in class_text
                and "mapped_column" in class_text
            ):
                candidates.append((path, node))

    unique = {}
    for path, node in candidates:
        unique[(str(path.resolve()), node.name)] = (path, node)

    found = list(unique.values())

    if len(found) != 1:
        detail = "\n".join(
            f" - {p.relative_to(PROJECT)} :: {n.name}"
            for p, n in found
        )
        raise RuntimeError(
            "Phải xác định được đúng 1 class SurveyPersonYearRecord.\n"
            f"Hiện tìm thấy {len(found)}:\n{detail}"
        )

    return found[0]


def find_insert_line(
    text: str,
    class_node: ast.ClassDef,
) -> int:
    # Ưu tiên chèn ngay sau completed_preschool_by_age hiện có.
    for item in class_node.body:
        target_name = None

        if isinstance(item, ast.AnnAssign):
            if isinstance(item.target, ast.Name):
                target_name = item.target.id

        elif isinstance(item, ast.Assign):
            if len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
                target_name = item.targets[0].id

        if target_name == "completed_preschool_by_age":
            return int(item.end_lineno)

    # Nếu model khác bố cục, chèn sau mapped_column cuối cùng trong class.
    last_line = None

    for item in class_node.body:
        item_text = ast.get_source_segment(text, item) or ""

        if "mapped_column" not in item_text:
            continue

        if isinstance(item, (ast.AnnAssign, ast.Assign)):
            last_line = int(item.end_lineno)

    if last_line is None:
        raise RuntimeError(
            "Không xác định được vị trí chèn field trong SurveyPersonYearRecord."
        )

    return last_line


def patch_model(path: Path) -> bool:
    text = read_text(path)

    if MARK_START in text:
        say(" - Model đã có marker 13B-11.13.1; không chèn lặp.")
        return False

    tree = ast.parse(text)
    target = None

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if node.name == "SurveyPersonYearRecord":
                target = node
                break

            class_text = ast.get_source_segment(text, node) or ""
            if (
                "survey_person_year_records" in class_text
                and "mapped_column" in class_text
            ):
                target = node
                break

    if target is None:
        raise RuntimeError(
            "Không tìm thấy class SurveyPersonYearRecord khi patch."
        )

    class_text = ast.get_source_segment(text, target) or ""

    # Không được tạo trùng field dù marker chưa có.
    for name, _, _, _ in NEW_COLUMNS:
        if (
            f"{name}:" in class_text
            or f"{name} =" in class_text
        ):
            raise RuntimeError(
                f"Model đã có field '{name}' nhưng không có marker Bài 13B-11.13.1. "
                "Dừng để tránh ghi đè."
            )

    if "Mapped[" not in class_text or "mapped_column" not in class_text:
        raise RuntimeError(
            "SurveyPersonYearRecord không dùng kiểu Mapped/mapped_column như dự kiến."
        )

    # Các type này phải đã tồn tại trong source vì model hiện tại đã dùng.
    if "Boolean" not in text:
        raise RuntimeError(
            "Model source chưa import/use Boolean; cần khảo sát riêng."
        )

    if "String" not in text:
        raise RuntimeError(
            "Model source chưa import/use String; cần khảo sát riêng."
        )

    insert_after_line = find_insert_line(text, target)

    lines = text.splitlines(keepends=True)
    block = "\n" + MODEL_FIELDS + "\n"

    lines[insert_after_line:insert_after_line] = [block]

    patched = "".join(lines)

    # Validate syntax before write.
    ast.parse(patched)
    write_text(path, patched)
    return True


def apply_db_columns() -> list[str]:
    conn = sqlite3.connect(str(DB_PATH))
    created: list[str] = []

    try:
        existing = {
            str(row[1])
            for row in conn.execute(
                f'PRAGMA table_info("{TABLE}")'
            ).fetchall()
        }

        for name, sql_type, default_sql, _ in NEW_COLUMNS:
            if name in existing:
                say(f" - DB đã có cột {name}: giữ nguyên.")
                continue

            sql = (
                f'ALTER TABLE "{TABLE}" '
                f'ADD COLUMN "{name}" {sql_type}'
            )

            if default_sql is not None:
                sql += f" NOT NULL DEFAULT {default_sql}"

            conn.execute(sql)
            created.append(name)
            say(f" - Đã tạo cột DB: {name}")

        conn.commit()
        return created

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def verify_model_file(path: Path) -> None:
    text = read_text(path)

    for name, _, _, _ in NEW_COLUMNS:
        if name not in text:
            raise RuntimeError(
                f"Model source thiếu field sau cài: {name}"
            )

    if MARK_START not in text or MARK_END not in text:
        raise RuntimeError(
            "Model source thiếu marker 13B-11.13.1."
        )

    ast.parse(text)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(path),
        ],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        say(result.stdout.rstrip())

    if result.stderr:
        say(result.stderr.rstrip())

    if result.returncode != 0:
        raise RuntimeError(
            f"py_compile không đạt: {path}"
        )


def verify_runtime_model(path: Path) -> None:
    relative = path.relative_to(PROJECT).with_suffix("")
    module_name = ".".join(relative.parts)

    # Đảm bảo import source mới, không dùng cache cũ.
    importlib.invalidate_caches()

    if module_name in sys.modules:
        del sys.modules[module_name]

    module = importlib.import_module(module_name)

    cls = getattr(
        module,
        "SurveyPersonYearRecord",
        None,
    )

    if cls is None:
        # Fallback class theo __tablename__
        for value in vars(module).values():
            if isinstance(value, type):
                if getattr(value, "__tablename__", None) == TABLE:
                    cls = value
                    break

    if cls is None:
        raise RuntimeError(
            "Import runtime không tìm thấy SurveyPersonYearRecord."
        )

    for name, _, _, _ in NEW_COLUMNS:
        if not hasattr(cls, name):
            raise RuntimeError(
                f"Runtime model thiếu attribute: {name}"
            )


def verify_db(
    count_before: int,
) -> None:
    columns = db_columns(DB_PATH)

    for name, _, _, _ in NEW_COLUMNS:
        if name not in columns:
            raise RuntimeError(
                f"Database thiếu cột sau cài: {name}"
            )

    count_after = db_count(DB_PATH)

    if count_after != count_before:
        raise RuntimeError(
            "Số bản ghi survey_person_year_records thay đổi: "
            f"{count_before} -> {count_after}"
        )

    integrity, fk_total = db_integrity(DB_PATH)

    if integrity.lower() != "ok":
        raise RuntimeError(
            f"integrity_check không đạt: {integrity}"
        )

    if fk_total != 0:
        raise RuntimeError(
            f"foreign_key_check phát hiện {fk_total} lỗi."
        )


def main() -> int:
    say("=" * 120)
    say(
        "BÀI 13B-11.13.1 - BỔ SUNG CẤU TRÚC DỮ LIỆU "
        "XMC + TIỂU HỌC + THCS"
    )
    say("=" * 120)
    say()
    say("MỤC TIÊU:")
    say(" - Bổ sung dữ liệu gốc phục vụ Xóa mù chữ.")
    say(" - Bổ sung hoàn thành chương trình Tiểu học.")
    say(" - Bổ sung hoàn thành chương trình THCS.")
    say(" - Bổ sung hướng học sau THCS.")
    say()
    say("CỘT MỚI:")
    for name, _, _, description in NEW_COLUMNS:
        say(f" - {name}: {description}")
    say()
    say("GIỮ NGUYÊN:")
    say(" - completed_preschool_5.")
    say(" - completed_preschool_by_age.")
    say(" - attends_required_days / attends_regularly.")
    say(" - prepared_vietnamese.")
    say(" - weight/height/underweight/stunted.")
    say(" - toàn bộ dữ liệu khuyết tật hiện có.")
    say(" - chưa sửa giao diện.")
    say(" - chưa sửa báo cáo.")
    say()
    say("AN TOÀN:")
    say(" - Backup database bằng SQLite Backup API.")
    say(" - Backup file model trước khi sửa.")
    say(" - Chỉ ADD COLUMN còn thiếu.")
    say(" - Không UPDATE dữ liệu 18 bản ghi hiện tại.")
    say(" - Rollback source + database nếu kiểm tra thất bại.")
    say()

    if not DB_PATH.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB_PATH}"
        )

    model_path, model_class = locate_model_source()

    say(
        "Model phát hiện: "
        f"{model_path.relative_to(PROJECT)} "
        f":: {model_class.name}"
    )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_model = (
        BACKUP
        / model_path.relative_to(PROJECT)
    )
    backup_model.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        model_path,
        backup_model,
    )

    backup_db = BACKUP / "phocap.db"
    sqlite_backup(
        DB_PATH,
        backup_db,
    )

    count_before = db_count(DB_PATH)

    say(f"Backup: {BACKUP}")
    say(
        "survey_person_year_records trước cài: "
        f"{count_before}"
    )

    try:
        changed_model = patch_model(
            model_path
        )

        verify_model_file(
            model_path
        )

        created_columns = apply_db_columns()

        verify_db(
            count_before
        )

        verify_runtime_model(
            model_path
        )

        say()
        say("KIỂM TRA SAU CÀI:")
        say(
            f" - Model source sửa mới: "
            f"{'CÓ' if changed_model else 'ĐÃ CÓ'}"
        )
        say(
            " - Cột DB tạo mới: "
            + (
                ", ".join(created_columns)
                if created_columns
                else "không có (đã tồn tại)"
            )
        )
        say(
            " - Số bản ghi giữ nguyên: "
            f"{count_before}"
        )
        say(" - py_compile model: OK")
        say(" - Runtime model attributes: OK")
        say(" - integrity_check: OK")
        say(" - foreign_key_check: 0 lỗi")
        say(" - Chỉ báo Mầm non: KHÔNG THAY ĐỔI")
        say()
        say(
            "CÀI ĐẶT BÀI 13B-11.13.1 THÀNH CÔNG"
        )

        return 0

    except Exception:
        traceback.print_exc()

        say()
        say(
            "CÓ LỖI - ĐANG KHÔI PHỤC SOURCE VÀ DATABASE..."
        )

        try:
            shutil.copy2(
                backup_model,
                model_path,
            )
            say(" - Đã khôi phục model source.")
        except Exception as exc:
            say(
                f" - LỖI khôi phục source: {exc}"
            )

        try:
            sqlite_restore(
                backup_db,
                DB_PATH,
            )
            say(" - Đã khôi phục database.")
        except Exception as exc:
            say(
                f" - LỖI khôi phục database: {exc}"
            )

        say("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
