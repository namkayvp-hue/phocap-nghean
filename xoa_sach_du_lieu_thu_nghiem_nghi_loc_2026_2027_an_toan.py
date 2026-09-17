# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import shutil
import sqlite3
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
DB_PATH = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

TARGET_YEAR_CODE = "2026-2027"
TARGET_COMMUNE_CODE = "17827"
TARGET_COMMUNE_NAME_TOKEN = "Nghi Lộc"
CONFIRM_TEXT = "XOA NGHI LOC 2026-2027"

DIRECT_BATCH_COLUMNS = (
    "survey_batch_id",
    "source_batch_id",
    "target_batch_id",
    "batch_id",
)

DIRECT_FORM_COLUMNS = (
    "survey_form_id",
    "source_form_id",
    "target_form_id",
)

# Không bao giờ seed trực tiếp các bảng lõi này để xóa.
# Công cụ chỉ xóa dữ liệu điều tra theo batch + hộ chỉ thuộc các batch mục tiêu.
ABSOLUTELY_PROTECTED = {
    "school_years",
    "communes",
    "schools",
    "users",
    "roles",
    "students",
    "student_enrollments",
    "staff",
    "staff_members",
    "staff_year_records",
    "classes",
}


def qi(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def placeholders(n: int) -> str:
    return ",".join("?" for _ in range(n))


def chunks(values, size=300):
    values = list(values)
    for i in range(0, len(values), size):
        yield values[i:i + size]


def tables(con: sqlite3.Connection) -> list[str]:
    return [
        str(r[0])
        for r in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(r[1])
        for r in con.execute(
            f"PRAGMA table_info({qi(table)})"
        ).fetchall()
    }


def foreign_keys(con: sqlite3.Connection, table: str):
    result = []
    for row in con.execute(
        f"PRAGMA foreign_key_list({qi(table)})"
    ).fetchall():
        result.append({
            "parent_table": str(row[2]),
            "child_col": str(row[3]),
            "parent_col": str(row[4]),
        })
    return result


def select_rowids_by_in(
    con: sqlite3.Connection,
    table: str,
    column: str,
    values: set,
) -> set[int]:
    if not values:
        return set()

    found: set[int] = set()
    for part in chunks(values):
        sql = (
            f"SELECT rowid FROM {qi(table)} "
            f"WHERE {qi(column)} IN ({placeholders(len(part))})"
        )
        for row in con.execute(sql, tuple(part)).fetchall():
            found.add(int(row[0]))
    return found


def selected_values(
    con: sqlite3.Connection,
    table: str,
    rowids: set[int],
    column: str,
) -> set:
    if not rowids:
        return set()

    values = set()
    for part in chunks(rowids):
        sql = (
            f"SELECT DISTINCT {qi(column)} "
            f"FROM {qi(table)} "
            f"WHERE rowid IN ({placeholders(len(part))}) "
            f"AND {qi(column)} IS NOT NULL"
        )
        for row in con.execute(sql, tuple(part)).fetchall():
            values.add(row[0])
    return values


def add_batch_scoped_rows(
    con: sqlite3.Connection,
    selected: dict[str, set[int]],
    reasons: dict[str, set[str]],
    batch_ids: set[int],
) -> None:
    all_tables = tables(con)
    col_map = {t: columns(con, t) for t in all_tables}

    selected["survey_batches"].update(
        select_rowids_by_in(
            con, "survey_batches", "id", batch_ids
        )
    )
    reasons["survey_batches"].add(
        "Đợt điều tra Xã Nghi Lộc năm 2026-2027"
    )

    for table in all_tables:
        if table in ABSOLUTELY_PROTECTED or table == "survey_batches":
            continue

        for col in DIRECT_BATCH_COLUMNS:
            if col not in col_map[table]:
                continue
            rows = select_rowids_by_in(
                con, table, col, batch_ids
            )
            if rows:
                selected[table].update(rows)
                reasons[table].add(f"{col} thuộc batch mục tiêu")


def target_household_ids(
    con: sqlite3.Connection,
    batch_ids: set[int],
) -> set[int]:
    if not batch_ids:
        return set()

    result: set[int] = set()
    for part in chunks(batch_ids):
        sql = f"""
            SELECT DISTINCT sf.household_id
            FROM survey_forms sf
            WHERE sf.survey_batch_id IN ({placeholders(len(part))})
              AND NOT EXISTS (
                    SELECT 1
                    FROM survey_forms other_sf
                    WHERE other_sf.household_id = sf.household_id
                      AND other_sf.survey_batch_id
                          NOT IN ({placeholders(len(batch_ids))})
              )
        """
        params = tuple(part) + tuple(batch_ids)
        for row in con.execute(sql, params).fetchall():
            result.add(int(row[0]))
    return result


def add_exclusive_households(
    con: sqlite3.Connection,
    selected: dict[str, set[int]],
    reasons: dict[str, set[str]],
    household_ids: set[int],
) -> None:
    if not household_ids:
        return

    selected["households"].update(
        select_rowids_by_in(
            con, "households", "id", household_ids
        )
    )
    reasons["households"].add(
        "Hộ chỉ xuất hiện trong các đợt Nghi Lộc 2026-2027 mục tiêu"
    )


def expand_children_by_fk_and_form_columns(
    con: sqlite3.Connection,
    selected: dict[str, set[int]],
    reasons: dict[str, set[str]],
) -> None:
    all_tables = tables(con)
    col_map = {t: columns(con, t) for t in all_tables}
    fk_map = {t: foreign_keys(con, t) for t in all_tables}

    changed = True
    while changed:
        changed = False

        # Child rows qua khóa ngoại từ mọi parent đã chọn.
        for child in all_tables:
            if child in ABSOLUTELY_PROTECTED:
                continue

            for fk in fk_map[child]:
                parent = fk["parent_table"]

                if parent not in selected or not selected[parent]:
                    continue
                if parent in ABSOLUTELY_PROTECTED:
                    continue

                parent_values = selected_values(
                    con,
                    parent,
                    selected[parent],
                    fk["parent_col"],
                )
                if not parent_values:
                    continue

                child_rows = select_rowids_by_in(
                    con,
                    child,
                    fk["child_col"],
                    parent_values,
                )

                before = len(selected[child])
                selected[child].update(child_rows)

                if len(selected[child]) > before:
                    reasons[child].add(
                        f"{fk['child_col']} -> "
                        f"{parent}.{fk['parent_col']}"
                    )
                    changed = True

        # Bảng cũ có survey_form_id nhưng không khai FK.
        if "survey_forms" in selected and selected["survey_forms"]:
            form_ids = selected_values(
                con,
                "survey_forms",
                selected["survey_forms"],
                "id",
            )
            for table in all_tables:
                if table in ABSOLUTELY_PROTECTED:
                    continue
                for col in DIRECT_FORM_COLUMNS:
                    if col not in col_map[table]:
                        continue
                    rows = select_rowids_by_in(
                        con, table, col, form_ids
                    )
                    before = len(selected[table])
                    selected[table].update(rows)
                    if len(selected[table]) > before:
                        reasons[table].add(
                            f"{col} thuộc phiếu mục tiêu"
                        )
                        changed = True

    # Tuyệt đối không để bảng lõi lọt vào.
    for table in list(selected):
        if table in ABSOLUTELY_PROTECTED:
            selected.pop(table, None)
            reasons.pop(table, None)


def delete_order(
    con: sqlite3.Connection,
    selected_tables: set[str],
) -> list[str]:
    # Edge child -> parent; child phải xóa trước parent.
    edges: dict[str, set[str]] = defaultdict(set)
    indegree = {t: 0 for t in selected_tables}

    for child in selected_tables:
        for fk in foreign_keys(con, child):
            parent = fk["parent_table"]
            if parent not in selected_tables or parent == child:
                continue
            if parent not in edges[child]:
                edges[child].add(parent)
                indegree[parent] += 1

    queue = deque(
        sorted(t for t, d in indegree.items() if d == 0)
    )
    order: list[str] = []

    while queue:
        table = queue.popleft()
        order.append(table)
        for parent in sorted(edges.get(table, set())):
            indegree[parent] -= 1
            if indegree[parent] == 0:
                queue.append(parent)

    if len(order) != len(selected_tables):
        unresolved = sorted(selected_tables.difference(order))
        raise RuntimeError(
            "Phát hiện vòng phụ thuộc: "
            + ", ".join(unresolved)
            + ". Dừng an toàn."
        )

    for last_table in ("households", "survey_batches"):
        if last_table in order:
            order.remove(last_table)
            order.append(last_table)

    return order


def backup_database(
    batch_codes: list[str],
    import_files: list[Path],
) -> Path:
    EXPORTS.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = (
        EXPORTS
        / f"backup_truoc_xoa_nghi_loc_2026_2027_{stamp}"
    )
    backup_dir.mkdir(parents=True, exist_ok=False)

    backup_db = backup_dir / "phocap.db"

    src = sqlite3.connect(str(DB_PATH), timeout=30)
    dst = sqlite3.connect(str(backup_db), timeout=30)
    try:
        src.execute("PRAGMA busy_timeout=30000")
        src.backup(dst, pages=1000, sleep=0.05)
        dst.commit()
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(str(backup_db))
    try:
        integrity = str(
            check.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )
        fk_errors = check.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    finally:
        check.close()

    if integrity.lower() != "ok" or fk_errors:
        raise RuntimeError(
            "Backup DB không đạt integrity/FK check. "
            "Dừng xóa."
        )

    files_backup = backup_dir / "tep_gia_dinh_da_tai_len"
    copied = []

    for src_path in import_files:
        try:
            src_path = src_path.resolve()
        except Exception:
            continue

        if not src_path.exists() or not src_path.is_file():
            continue

        # Chỉ cho backup file nằm trong project.
        try:
            rel = src_path.relative_to(PROJECT)
        except ValueError:
            continue

        dst_path = files_backup / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        copied.append(str(rel))

    metadata = {
        "backup_type": "before_delete_nghi_loc_2026_2027_test_data",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target_year_code": TARGET_YEAR_CODE,
        "target_commune_code": TARGET_COMMUNE_CODE,
        "target_commune_name_token": TARGET_COMMUNE_NAME_TOKEN,
        "batch_codes": batch_codes,
        "database_source": str(DB_PATH),
        "database_backup": str(backup_db),
        "copied_import_files": copied,
        "integrity_check": integrity,
        "foreign_key_check_total": len(fk_errors),
    }

    (backup_dir / "thong_tin_backup.json").write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return backup_dir


def collect_import_files(
    con: sqlite3.Connection,
    batch_ids: set[int],
) -> tuple[list[Path], list[dict]]:
    if (
        "survey_household_import_jobs" not in tables(con)
        or not batch_ids
    ):
        return [], []

    rows = []
    files = []

    for part in chunks(batch_ids):
        sql = f"""
            SELECT id, job_code, original_file_name, stored_path,
                   status, message
            FROM survey_household_import_jobs
            WHERE survey_batch_id IN ({placeholders(len(part))})
            ORDER BY id
        """
        for row in con.execute(sql, tuple(part)).fetchall():
            item = dict(row)
            rows.append(item)

            stored_path = str(item.get("stored_path") or "").strip()
            if not stored_path:
                continue

            p = Path(stored_path)
            if not p.is_absolute():
                p = PROJECT / p
            files.append(p)

    return files, rows


def remove_import_files_after_commit(
    import_files: list[Path],
    backup_dir: Path,
) -> list[str]:
    removed = []

    for path in import_files:
        try:
            resolved = path.resolve()
            resolved.relative_to(PROJECT)
        except Exception:
            continue

        if not resolved.exists() or not resolved.is_file():
            continue

        # Không bao giờ đụng vào chính backup vừa tạo.
        try:
            resolved.relative_to(backup_dir.resolve())
            continue
        except ValueError:
            pass

        try:
            resolved.unlink()
            removed.append(str(resolved))

            # Dọn thư mục job rỗng, tối đa đến household_imports.
            parent = resolved.parent
            stop = (PROJECT / "exports" / "household_imports").resolve()

            while parent.exists() and parent != stop:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        except Exception:
            pass

    return removed


def count_selected(
    selected: dict[str, set[int]]
) -> int:
    return sum(len(v) for v in selected.values())


def remaining_batch_refs(
    con: sqlite3.Connection,
    batch_ids: set[int],
) -> list[tuple[str, str, int]]:
    result = []

    for table in tables(con):
        if table == "survey_batches":
            continue

        cols = columns(con, table)

        for col in DIRECT_BATCH_COLUMNS:
            if col not in cols:
                continue

            total = 0
            for part in chunks(batch_ids):
                total += int(
                    con.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM {qi(table)}
                        WHERE {qi(col)}
                        IN ({placeholders(len(part))})
                        """,
                        tuple(part),
                    ).fetchone()[0]
                    or 0
                )

            if total:
                result.append((table, col, total))

    return result


def main() -> int:
    print("=" * 112)
    print(
        "XÓA SẠCH DỮ LIỆU THỬ NGHIỆM XÃ NGHI LỘC "
        "NĂM HỌC 2026-2027 - AN TOÀN"
    )
    print("=" * 112)
    print()
    print("PHẠM VI:")
    print(" - Chỉ Xã Nghi Lộc, mã 17827.")
    print(" - Chỉ năm học 2026-2027.")
    print(" - Tất cả survey_batches của đúng phạm vi trên.")
    print(" - Phiếu, phân công, tổ điều tra, nhật ký, import jobs")
    print("   và dữ liệu con của các đợt đó.")
    print(" - Hộ + thành viên chỉ khi hộ đó KHÔNG được dùng ở batch khác.")
    print(" - File Excel giả định đã upload qua import job được backup rồi xóa.")
    print()
    print("KHÔNG XÓA:")
    print(" - Xã/phường, trường, tài khoản.")
    print(" - Danh mục năm học, lớp.")
    print(" - Học sinh, dữ liệu học sinh, đội ngũ.")
    print(" - Bất kỳ batch/xã nào ngoài Nghi Lộc 2026-2027.")
    print()

    if not DB_PATH.exists():
        print("KHÔNG TÌM THẤY DB:", DB_PATH)
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row

    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")

        integrity = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_errors = con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        print("Database integrity_check:", integrity)
        print("Database foreign_key_check:", len(fk_errors), "lỗi")

        if integrity.lower() != "ok" or fk_errors:
            print("DỪNG AN TOÀN: DB hiện tại chưa đạt kiểm tra.")
            return 2

        year = con.execute(
            """
            SELECT id, code, name
            FROM school_years
            WHERE code=?
            LIMIT 1
            """,
            (TARGET_YEAR_CODE,),
        ).fetchone()

        commune = con.execute(
            """
            SELECT id, code, name, is_active
            FROM communes
            WHERE code=?
            LIMIT 1
            """,
            (TARGET_COMMUNE_CODE,),
        ).fetchone()

        if year is None:
            print("DỪNG: không tìm thấy năm học", TARGET_YEAR_CODE)
            return 3

        if commune is None:
            print("DỪNG: không tìm thấy xã mã", TARGET_COMMUNE_CODE)
            return 4

        if TARGET_COMMUNE_NAME_TOKEN.lower() not in str(
            commune["name"]
        ).lower():
            print(
                "DỪNG AN TOÀN: mã xã 17827 hiện không có tên Nghi Lộc:",
                commune["name"],
            )
            return 5

        year_id = int(year["id"])
        commune_id = int(commune["id"])

        batches = con.execute(
            """
            SELECT
                sb.id,
                sb.code,
                sb.name,
                sb.status,
                COALESCE(sb.is_locked, 0) AS is_locked,
                (
                    SELECT COUNT(*)
                    FROM survey_forms sf
                    WHERE sf.survey_batch_id=sb.id
                ) AS form_total
            FROM survey_batches sb
            WHERE sb.school_year_id=?
              AND sb.commune_id=?
            ORDER BY sb.id
            """,
            (year_id, commune_id),
        ).fetchall()

        if not batches:
            print(
                "Nghi Lộc 2026-2027 hiện không còn đợt điều tra. "
                "Không có gì bị xóa."
            )
            return 0

        batch_ids = {int(r["id"]) for r in batches}
        batch_codes = [str(r["code"]) for r in batches]

        print()
        print(
            f"TÌM THẤY {len(batches)} ĐỢT CỦA "
            f"{commune['name']} / {TARGET_YEAR_CODE}:"
        )
        for r in batches:
            print(
                f" - id={r['id']} | {r['code']} | {r['status']} | "
                f"locked={int(r['is_locked'])} | "
                f"phiếu={int(r['form_total'])} | {r['name']}"
            )

        import_files, import_jobs = collect_import_files(
            con, batch_ids
        )

        print()
        print(f"IMPORT JOBS/FILE GIẢ ĐỊNH: {len(import_jobs)}")
        for item in import_jobs:
            print(
                f" - {item['job_code']} | "
                f"{item['original_file_name']} | "
                f"{item['status']}"
            )

        selected: dict[str, set[int]] = defaultdict(set)
        reasons: dict[str, set[str]] = defaultdict(set)

        add_batch_scoped_rows(
            con, selected, reasons, batch_ids
        )

        exclusive_households = target_household_ids(
            con, batch_ids
        )

        add_exclusive_households(
            con,
            selected,
            reasons,
            exclusive_households,
        )

        expand_children_by_fk_and_form_columns(
            con,
            selected,
            reasons,
        )

        selected = {
            t: ids for t, ids in selected.items() if ids
        }

        order = delete_order(
            con,
            set(selected),
        )

        print()
        print("XEM TRƯỚC CÁC BẢNG SẼ XÓA:")
        for table in order:
            print(
                f" - {table}: {len(selected[table])} dòng"
                f" | {', '.join(sorted(reasons.get(table, set())))}"
            )

        print()
        print("TỔNG SỐ DÒNG DỰ KIẾN XÓA:", count_selected(selected))
        print("HỘ CHỈ THUỘC ĐỢT MỤC TIÊU SẼ XÓA:", len(exclusive_households))
        print("FILE IMPORT SẼ BACKUP RỒI XÓA:", len(import_files))
        print()

        entered = input(
            "Nếu đúng phạm vi, nhập chính xác: "
            f"{CONFIRM_TEXT}\n> "
        ).strip()

        if entered != CONFIRM_TEXT:
            print("ĐÃ HỦY. Không có dữ liệu nào bị xóa.")
            return 0

        con.close()

        backup_dir = backup_database(
            batch_codes,
            import_files,
        )
        print()
        print("ĐÃ BACKUP TOÀN BỘ DB + FILE IMPORT:")
        print(" ", backup_dir)

        # Mở lại DB để xóa trong giao dịch khóa ghi.
        con = sqlite3.connect(str(DB_PATH), timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")

        try:
            con.execute("BEGIN IMMEDIATE")

            # Kiểm tra lại đúng batch ngay trong transaction.
            current_ids = {
                int(r[0])
                for r in con.execute(
                    """
                    SELECT id
                    FROM survey_batches
                    WHERE school_year_id=?
                      AND commune_id=?
                    """,
                    (year_id, commune_id),
                ).fetchall()
            }

            if current_ids != batch_ids:
                raise RuntimeError(
                    "Danh sách batch đã thay đổi sau khi xem trước. "
                    "Rollback để tránh xóa nhầm."
                )

            # Xóa theo rowid chính xác đã preview.
            for table in order:
                rowids = selected[table]
                for part in chunks(rowids):
                    con.execute(
                        f"""
                        DELETE FROM {qi(table)}
                        WHERE rowid IN ({placeholders(len(part))})
                        """,
                        tuple(part),
                    )

            # Không còn batch mục tiêu.
            left_batches = int(
                con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM survey_batches
                    WHERE id IN ({placeholders(len(batch_ids))})
                    """,
                    tuple(batch_ids),
                ).fetchone()[0]
                or 0
            )
            if left_batches:
                raise RuntimeError(
                    f"Còn {left_batches} batch mục tiêu sau DELETE."
                )

            refs = remaining_batch_refs(
                con, batch_ids
            )
            if refs:
                raise RuntimeError(
                    "Còn tham chiếu batch sau DELETE: "
                    + repr(refs[:20])
                )

            integrity2 = str(
                con.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            )
            fk2 = con.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()

            if integrity2.lower() != "ok" or fk2:
                raise RuntimeError(
                    "Kiểm tra DB sau DELETE không đạt. "
                    "Rollback toàn bộ."
                )

            con.commit()

        except Exception:
            con.rollback()
            raise

        removed_files = remove_import_files_after_commit(
            import_files,
            backup_dir,
        )

        report_path = (
            EXPORTS
            / (
                "bao_cao_xoa_sach_nghi_loc_2026_2027_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
                + ".txt"
            )
        )

        report_lines = [
            "XÓA SẠCH DỮ LIỆU THỬ NGHIỆM NGHI LỘC 2026-2027",
            f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
            f"Xã: {commune['name']} | code={commune['code']} | id={commune_id}",
            f"Năm học: {TARGET_YEAR_CODE} | id={year_id}",
            f"Batch đã xóa: {batch_codes}",
            f"Tổng dòng DB đã xóa: {count_selected(selected)}",
            f"Hộ độc quyền đã xóa: {len(exclusive_households)}",
            f"Import jobs: {len(import_jobs)}",
            f"File import đã xóa khỏi vị trí hoạt động: {len(removed_files)}",
            f"Backup: {backup_dir}",
            "integrity_check sau xóa: ok",
            "foreign_key_check sau xóa: 0 lỗi",
            "",
            "CÁC BẢNG ĐÃ XÓA:",
        ]

        for table in order:
            report_lines.append(
                f"- {table}: {len(selected[table])}"
            )

        report_lines.append("")
        report_lines.append("FILE IMPORT ĐÃ XÓA:")
        for p in removed_files:
            report_lines.append(f"- {p}")

        report_path.write_text(
            "\n".join(report_lines) + "\n",
            encoding="utf-8-sig",
        )

        print()
        print("=" * 112)
        print("XÓA THÀNH CÔNG DỮ LIỆU THỬ NGHIỆM NGHI LỘC 2026-2027")
        print("=" * 112)
        print("Batch đã xóa:", ", ".join(batch_codes))
        print("Backup:", backup_dir)
        print("Báo cáo:", report_path)
        print("integrity_check: ok")
        print("foreign_key_check: 0 lỗi")
        print()
        print(
            "Bây giờ có thể khởi động lại Uvicorn và tạo/khởi tạo "
            "đợt Nghi Lộc sạch theo quy trình mới."
        )

        return 0

    except Exception as exc:
        print()
        print("DỪNG / ROLLBACK AN TOÀN")
        print(type(exc).__name__ + ":", exc)
        print("Không xóa tiếp. Nếu backup đã tạo, giữ nguyên backup đó.")
        return 9

    finally:
        try:
            con.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
