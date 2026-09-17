# -*- coding: utf-8 -*-
"""
KHẢO SÁT 3 PHƯƠNG ÁN THCS CÒN LẠI - CHỈ ĐỌC

Mục tiêu:
- Xác định chính xác:
    QD3805-OP-0108
    QD3805-OP-0210
    QD3805-OP-0644
- Tìm THCS Mậu Đôn.
- Xác định source / target / plan.
- Thống kê dấu vết dữ liệu theo school_id.
- KHÔNG ghi database.
- KHÔNG sáp nhập.
- KHÔNG sửa file nguồn.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


# ============================================================
# UTF-8
# ============================================================

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ============================================================
# CẤU HÌNH
# ============================================================

OPERATION_CODES = [
    "QD3805-OP-0108",
    "QD3805-OP-0210",
    "QD3805-OP-0644",
]

SCHOOL_SEARCH_TERMS = [
    "Mậu Đôn",
    "Mau Don",
]

TEXT_COLUMN_HINTS = (
    "operation",
    "plan",
    "summary",
    "json",
    "source",
    "target",
    "school",
    "name",
    "code",
    "official",
    "merger",
)


# ============================================================
# HÀM TIỆN ÍCH
# ============================================================

def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_db() -> Path:
    root = Path(__file__).resolve().parent

    preferred = root / "phocap.db"
    if preferred.exists():
        return preferred

    candidates = []

    for p in root.rglob("phocap.db"):
        parts_lower = [x.lower() for x in p.parts]

        # Không lấy database nằm trong thư mục backup
        if any(
            "backup" in x
            or "sao_luu" in x
            or "saoluu" in x
            for x in parts_lower
        ):
            continue

        candidates.append(p)

    candidates = sorted(set(candidates))

    if len(candidates) == 1:
        return candidates[0]

    print("\nDỪNG AN TOÀN.")
    print("Không xác định duy nhất file phocap.db.")

    if not candidates:
        print("Không tìm thấy phocap.db.")
    else:
        print("Các file tìm thấy:")
        for p in candidates:
            print(" -", p)

    sys.exit(2)


def get_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()

    return [r[0] for r in rows]


def table_columns(
    conn: sqlite3.Connection,
    table: str,
) -> list[dict[str, Any]]:

    rows = conn.execute(
        f"PRAGMA table_info({qident(table)})"
    ).fetchall()

    result = []

    for r in rows:
        result.append(
            {
                "cid": r[0],
                "name": r[1],
                "type": r[2] or "",
                "notnull": r[3],
                "default": r[4],
                "pk": r[5],
            }
        )

    return result


def shorten(value: Any, max_len: int = 1000) -> Any:
    if value is None:
        return None

    if isinstance(value, (bytes, bytearray)):
        return f"<BLOB {len(value)} bytes>"

    if not isinstance(value, str):
        return value

    if len(value) <= max_len:
        return value

    return value[:max_len] + "...<CUT>"


def row_to_dict(
    columns: list[str],
    row: tuple,
) -> dict[str, Any]:

    return {
        columns[i]: shorten(row[i])
        for i in range(len(columns))
    }


def print_json(data: Any):
    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


def looks_textual(col_type: str) -> bool:
    t = (col_type or "").upper()

    if not t:
        return True

    return any(
        x in t
        for x in (
            "CHAR",
            "TEXT",
            "CLOB",
            "JSON",
            "VARCHAR",
        )
    )


# ============================================================
# TÌM CHUỖI TRONG DATABASE
# ============================================================

def search_term(
    conn: sqlite3.Connection,
    tables: list[str],
    term: str,
) -> list[dict[str, Any]]:

    matches = []

    for table in tables:
        cols = table_columns(conn, table)

        searchable = []

        for col in cols:
            name_lower = col["name"].lower()

            if not looks_textual(col["type"]):
                continue

            if any(h in name_lower for h in TEXT_COLUMN_HINTS):
                searchable.append(col["name"])

        if not searchable:
            continue

        conditions = [
            f"CAST({qident(c)} AS TEXT) LIKE ?"
            for c in searchable
        ]

        sql = (
            f"SELECT * FROM {qident(table)} "
            f"WHERE {' OR '.join(conditions)} "
            f"LIMIT 50"
        )

        params = [f"%{term}%"] * len(searchable)

        try:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()

            if not rows:
                continue

            names = [d[0] for d in cur.description]

            for row in rows:
                matches.append(
                    {
                        "table": table,
                        "row": row_to_dict(names, row),
                    }
                )

        except sqlite3.Error as exc:
            print(
                f"[CẢNH BÁO] Không đọc được "
                f"{table}: {exc}"
            )

    return matches


# ============================================================
# THU THẬP SCHOOL_ID
# ============================================================

def add_school_ids_from_object(
    obj: Any,
    result: set[int],
    parent_key: str = "",
):

    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).lower()

            if (
                key == "school_id"
                or key.endswith("_school_id")
            ):
                try:
                    if v is not None:
                        result.add(int(v))
                except Exception:
                    pass

            elif (
                key == "school_ids"
                or key.endswith("_school_ids")
                or "school_ids" in key
            ):
                if isinstance(v, list):
                    for x in v:
                        try:
                            result.add(int(x))
                        except Exception:
                            pass

                elif isinstance(v, str):
                    try:
                        parsed = json.loads(v)
                        add_school_ids_from_object(
                            {key: parsed},
                            result,
                        )
                    except Exception:
                        pass

            add_school_ids_from_object(v, result, key)

    elif isinstance(obj, list):
        for item in obj:
            add_school_ids_from_object(
                item,
                result,
                parent_key,
            )

    elif isinstance(obj, str):
        text = obj.strip()

        if (
            (text.startswith("{") and text.endswith("}"))
            or
            (text.startswith("[") and text.endswith("]"))
        ):
            try:
                parsed = json.loads(text)
                add_school_ids_from_object(
                    parsed,
                    result,
                    parent_key,
                )
            except Exception:
                pass


def collect_school_ids(
    matches: list[dict[str, Any]],
) -> set[int]:

    result: set[int] = set()

    for item in matches:
        table = item["table"]
        row = item["row"]

        add_school_ids_from_object(row, result)

        # Nếu đây là bảng trường và dòng tìm thấy bằng tên trường,
        # lấy luôn trường id.
        if "school" in table.lower():
            if "id" in row:
                try:
                    result.add(int(row["id"]))
                except Exception:
                    pass

    return result


# ============================================================
# TÌM THÔNG TIN TRƯỜNG
# ============================================================

def find_school_rows(
    conn: sqlite3.Connection,
    tables: list[str],
    school_ids: set[int],
) -> list[dict[str, Any]]:

    result = []

    if not school_ids:
        return result

    for table in tables:
        if "school" not in table.lower():
            continue

        cols = table_columns(conn, table)
        col_names = [c["name"] for c in cols]

        if "id" not in col_names:
            continue

        placeholders = ",".join(
            "?" for _ in school_ids
        )

        sql = (
            f"SELECT * FROM {qident(table)} "
            f"WHERE {qident('id')} IN ({placeholders})"
        )

        try:
            cur = conn.execute(
                sql,
                tuple(sorted(school_ids)),
            )
            rows = cur.fetchall()

            if not rows:
                continue

            names = [d[0] for d in cur.description]

            for row in rows:
                result.append(
                    {
                        "table": table,
                        "row": row_to_dict(names, row),
                    }
                )

        except sqlite3.Error:
            continue

    return result


# ============================================================
# THỐNG KÊ DẤU VẾT DỮ LIỆU THEO SCHOOL_ID
# ============================================================

def footprint_by_school(
    conn: sqlite3.Connection,
    tables: list[str],
    school_id: int,
):

    print()
    print("=" * 140)
    print(f"DẤU VẾT DỮ LIỆU SCHOOL_ID = {school_id}")
    print("=" * 140)

    found_any = False

    for table in tables:
        cols = table_columns(conn, table)
        col_names = [c["name"] for c in cols]

        school_columns = []

        for name in col_names:
            lower = name.lower()

            if (
                lower == "school_id"
                or lower.endswith("_school_id")
            ):
                # Không nhầm school_year_id với school_id
                if lower == "school_year_id":
                    continue

                school_columns.append(name)

        if not school_columns:
            continue

        for school_col in school_columns:
            try:
                total = conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {qident(table)}
                    WHERE {qident(school_col)} = ?
                    """,
                    (school_id,),
                ).fetchone()[0]

            except sqlite3.Error:
                continue

            if not total:
                continue

            found_any = True

            print(
                f"{table}"
                f" | {school_col}"
                f" | total = {total}"
            )

            # Nếu có school_year_id thì in theo năm
            if "school_year_id" in col_names:
                try:
                    rows = conn.execute(
                        f"""
                        SELECT
                            {qident('school_year_id')},
                            COUNT(*)
                        FROM {qident(table)}
                        WHERE {qident(school_col)} = ?
                        GROUP BY {qident('school_year_id')}
                        ORDER BY {qident('school_year_id')}
                        """,
                        (school_id,),
                    ).fetchall()

                    for year_id, count in rows:
                        print(
                            f"    school_year_id="
                            f"{year_id} -> {count}"
                        )

                except sqlite3.Error:
                    pass

    if not found_any:
        print("Không thấy bản ghi nào tham chiếu school_id này.")


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 140)
    print(
        "KHẢO SÁT 3 THCS ĐẶC THÙ CÒN LẠI "
        "- XÁC ĐỊNH THCS MẬU ĐÔN - CHỈ ĐỌC"
    )
    print("=" * 140)

    db_path = find_db()

    print("DATABASE =", db_path)

    sha_before = sha256_file(db_path)

    print("DB SHA BEFORE =", sha_before)
    print(
        "phocap.db-wal =",
        (db_path.parent / "phocap.db-wal").stat().st_size
        if (db_path.parent / "phocap.db-wal").exists()
        else 0,
    )
    print(
        "phocap.db-journal =",
        (db_path.parent / "phocap.db-journal").stat().st_size
        if (db_path.parent / "phocap.db-journal").exists()
        else 0,
    )

    print()
    print("MỞ DATABASE: READ-ONLY")

    uri = db_path.resolve().as_uri() + "?mode=ro"

    conn = sqlite3.connect(
        uri,
        uri=True,
        timeout=30,
    )

    try:
        conn.execute("PRAGMA query_only = ON")

        print()
        print("1. DATABASE HEALTH")
        print("-" * 140)

        integrity = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        fk = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        print("integrity =", integrity)
        print("FK =", len(fk))

        if integrity != "ok" or fk:
            print()
            print("DỪNG AN TOÀN.")
            print("Database health không đạt.")
            return

        tables = get_tables(conn)

        print()
        print("2. TÌM 3 OPERATION")
        print("-" * 140)

        all_matches: list[dict[str, Any]] = []

        for op in OPERATION_CODES:
            print()
            print("#" * 140)
            print("SEARCH =", op)
            print("#" * 140)

            matches = search_term(
                conn,
                tables,
                op,
            )

            print("MATCHES =", len(matches))

            if not matches:
                print("KHÔNG TÌM THẤY")
            else:
                for i, item in enumerate(
                    matches,
                    start=1,
                ):
                    print()
                    print(
                        f"[{i}] TABLE = "
                        f"{item['table']}"
                    )
                    print_json(item["row"])

            all_matches.extend(matches)

        print()
        print("=" * 140)
        print("3. TÌM THCS MẬU ĐÔN")
        print("=" * 140)

        mau_don_matches = []

        for term in SCHOOL_SEARCH_TERMS:
            print()
            print("SEARCH SCHOOL TERM =", term)

            matches = search_term(
                conn,
                tables,
                term,
            )

            print("MATCHES =", len(matches))

            for i, item in enumerate(
                matches,
                start=1,
            ):
                print()
                print(
                    f"[{i}] TABLE = "
                    f"{item['table']}"
                )
                print_json(item["row"])

            mau_don_matches.extend(matches)

        print()
        print("=" * 140)
        print("4. SCHOOL IDs PHÁT HIỆN")
        print("=" * 140)

        all_search_matches = (
            all_matches
            + mau_don_matches
        )

        school_ids = collect_school_ids(
            all_search_matches
        )

        print(
            "SCHOOL IDS =",
            sorted(school_ids),
        )

        print()
        print("=" * 140)
        print("5. THÔNG TIN CÁC TRƯỜNG LIÊN QUAN")
        print("=" * 140)

        school_rows = find_school_rows(
            conn,
            tables,
            school_ids,
        )

        if not school_rows:
            print(
                "Không tìm thấy thêm bản ghi "
                "trong các bảng school."
            )
        else:
            for item in school_rows:
                print()
                print(
                    "TABLE =",
                    item["table"],
                )
                print_json(item["row"])

        print()
        print("=" * 140)
        print("6. DẤU VẾT DỮ LIỆU CỦA TỪNG TRƯỜNG")
        print("=" * 140)

        for school_id in sorted(school_ids):
            footprint_by_school(
                conn,
                tables,
                school_id,
            )

        print()
        print("=" * 140)
        print("7. KẾT LUẬN KHẢO SÁT")
        print("=" * 140)

        print(
            "Đã khảo sát:",
            ", ".join(OPERATION_CODES),
        )
        print(
            "Đã tìm tên trường:",
            ", ".join(SCHOOL_SEARCH_TERMS),
        )
        print(
            "SCHOOL IDS phát hiện:",
            sorted(school_ids),
        )

        print()
        print(
            "KHÔNG INSERT / UPDATE / DELETE."
        )
        print(
            "KHÔNG THỰC HIỆN SÁP NHẬP."
        )

    finally:
        conn.close()

    sha_after = sha256_file(db_path)

    print()
    print("=" * 140)
    print("8. FILE SAFETY")
    print("=" * 140)

    print(
        "DB:",
        sha_before,
        "->",
        sha_after,
    )

    if sha_before != sha_after:
        print()
        print(
            "CẢNH BÁO: SHA DATABASE ĐÃ THAY ĐỔI."
        )
        print(
            "DỪNG - KHÔNG THỰC HIỆN BƯỚC TIẾP."
        )
        sys.exit(3)

    print()
    print("=" * 140)
    print("KHẢO SÁT HOÀN TẤT")
    print("DATABASE = KHÔNG THAY ĐỔI")
    print("KHÔNG SÁP NHẬP BẤT KỲ TRƯỜNG NÀO")
    print("=" * 140)


if __name__ == "__main__":
    main()