# -*- coding: utf-8 -*-
r"""
DRY-RUN V9.1 - KIỂM TRA 7 LOG KHÔNG CÓ school_year_id
======================================================

V9 còn đúng 2 bảng cần policy:
- survey_execution_workflow_logs : 1 row ở trường nguồn
- survey_team_registration_logs  : 6 rows ở trường nguồn

MỤC TIÊU
--------
- CHỈ ĐỌC database.
- Liệt kê đầy đủ 7 log.
- Đọc schema + foreign keys.
- Truy các khóa FK trực tiếp.
- Truy thêm survey_batch_id / team_id / assignment_id nếu có.
- Tìm school_year_id gián tiếp từ bảng cha.
- Kiểm tra có bảng con nào phụ thuộc vào log hay không.
- Xác định policy an toàn:
    KEEP_AUDIT_LOG_AT_ORIGINAL_SOURCE
    hoặc REVIEW_BUSINESS_STATE
- Không sửa database.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_7_log_khong_co_nam_truoc_dong_co_sap_nhap_v9_1.py
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(r"C:\PhoCap")
DB_PATH = PROJECT_ROOT / "data" / "phocap.db"

SOURCE_IDS = (749, 750, 751, 1180, 1181, 1607, 1608)
TARGET_YEAR_EXPECTED = 2

LOG_TABLES = (
    "survey_execution_workflow_logs",
    "survey_team_registration_logs",
)


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def all_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    return [
        {
            "cid": r[0],
            "name": r[1],
            "type": r[2],
            "notnull": r[3],
            "default": r[4],
            "pk": r[5],
        }
        for r in rows
    ]


def colset(conn: sqlite3.Connection, table: str) -> set[str]:
    return {x["name"] for x in columns(conn, table)}


def foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA foreign_key_list({qident(table)})").fetchall()
    return [
        {
            "id": r[0],
            "seq": r[1],
            "ref_table": r[2],
            "from_col": r[3],
            "to_col": r[4] or "id",
            "on_update": r[5],
            "on_delete": r[6],
        }
        for r in rows
    ]


def child_relations(conn: sqlite3.Connection, parent: str) -> list[dict]:
    out = []
    for table in all_tables(conn):
        for fk in foreign_keys(conn, table):
            if fk["ref_table"] == parent:
                out.append({
                    "parent_table": parent,
                    "child_table": table,
                    "child_from_col": fk["from_col"],
                    "parent_to_col": fk["to_col"],
                })
    return out


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def row_to_flat(table: str, row: sqlite3.Row) -> dict:
    d = {"table": table}
    for k in row.keys():
        value = row[k]
        d[k] = "" if value is None else value
    return d


def fetch_parent(
    conn: sqlite3.Connection,
    ref_table: str,
    ref_col: str,
    value,
) -> sqlite3.Row | None:
    if value is None or not table_exists(conn, ref_table):
        return None
    return conn.execute(
        f"SELECT * FROM {qident(ref_table)} "
        f"WHERE {qident(ref_col)}=? LIMIT 1",
        (value,),
    ).fetchone()


def detect_indirect_year(
    conn: sqlite3.Connection,
    table: str,
    row: sqlite3.Row,
) -> tuple[str, str, str]:
    """
    Trả:
    year_id, path, note

    Tìm theo:
    - FK trực tiếp đến bảng có school_year_id
    - survey_batch_id -> survey_batches.school_year_id
    - team_id -> survey_investigation_teams -> survey_batch_id -> survey_batches
    - assignment_id -> bảng assignment -> survey_batch_id/school_year_id
    """
    cs = colset(conn, table)

    # 1. FK trực tiếp.
    for fk in foreign_keys(conn, table):
        if fk["from_col"] not in cs:
            continue
        value = row[fk["from_col"]]
        parent = fetch_parent(
            conn, fk["ref_table"], fk["to_col"], value
        )
        if parent is None:
            continue
        pcs = set(parent.keys())

        if "school_year_id" in pcs and parent["school_year_id"] is not None:
            return (
                str(parent["school_year_id"]),
                f"{table}.{fk['from_col']} -> {fk['ref_table']}.school_year_id",
                "Tìm thấy năm học qua FK trực tiếp.",
            )

        # Nếu parent có survey_batch_id.
        if "survey_batch_id" in pcs and parent["survey_batch_id"] is not None:
            if table_exists(conn, "survey_batches"):
                b = conn.execute(
                    "SELECT * FROM survey_batches WHERE id=?",
                    (parent["survey_batch_id"],),
                ).fetchone()
                if b and "school_year_id" in b.keys():
                    return (
                        str(b["school_year_id"]),
                        (
                            f"{table}.{fk['from_col']} -> "
                            f"{fk['ref_table']}.survey_batch_id -> "
                            "survey_batches.school_year_id"
                        ),
                        "Tìm thấy năm học qua survey_batch.",
                    )

    # 2. Cột survey_batch_id trực tiếp dù không khai báo FK.
    if "survey_batch_id" in cs and row["survey_batch_id"] is not None:
        if table_exists(conn, "survey_batches"):
            b = conn.execute(
                "SELECT * FROM survey_batches WHERE id=?",
                (row["survey_batch_id"],),
            ).fetchone()
            if b and "school_year_id" in b.keys():
                return (
                    str(b["school_year_id"]),
                    f"{table}.survey_batch_id -> survey_batches.school_year_id",
                    "Tìm thấy năm học qua survey_batch_id.",
                )

    # 3. team_id.
    if "team_id" in cs and row["team_id"] is not None:
        if table_exists(conn, "survey_investigation_teams"):
            t = conn.execute(
                "SELECT * FROM survey_investigation_teams WHERE id=?",
                (row["team_id"],),
            ).fetchone()
            if t:
                if "school_year_id" in t.keys() and t["school_year_id"] is not None:
                    return (
                        str(t["school_year_id"]),
                        f"{table}.team_id -> survey_investigation_teams.school_year_id",
                        "Tìm thấy năm học qua team.",
                    )
                if "survey_batch_id" in t.keys() and t["survey_batch_id"] is not None:
                    if table_exists(conn, "survey_batches"):
                        b = conn.execute(
                            "SELECT * FROM survey_batches WHERE id=?",
                            (t["survey_batch_id"],),
                        ).fetchone()
                        if b and "school_year_id" in b.keys():
                            return (
                                str(b["school_year_id"]),
                                (
                                    f"{table}.team_id -> survey_investigation_teams."
                                    "survey_batch_id -> survey_batches.school_year_id"
                                ),
                                "Tìm thấy năm học qua team -> batch.",
                            )

    return "", "", "Không truy được school_year_id gián tiếp."


def main_audit() -> None:
    print("=" * 118)
    print("DRY-RUN V9.1 - KIỂM TRA 7 LOG KHÔNG CÓ school_year_id")
    print("=" * 118)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not DB_PATH.exists():
        raise AuditAbort(f"Không tìm thấy database: {DB_PATH}")

    conn = connect_ro(DB_PATH)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / f"dry_run_7_log_khong_co_nam_v9_1_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise AuditAbort(f"integrity_check={integrity}")

        schema_rows = []
        fk_rows = []
        child_rows = []
        raw_rows = []
        trace_rows = []
        parent_rows = []

        total_source_logs = 0
        unresolved = 0
        business_state_risk = 0

        for table in LOG_TABLES:
            if not table_exists(conn, table):
                raise AuditAbort(f"Không có bảng {table}")

            cs = colset(conn, table)
            if "school_id" not in cs:
                raise AuditAbort(f"{table} không có school_id")

            for x in columns(conn, table):
                schema_rows.append({"table": table, **x})
            for x in foreign_keys(conn, table):
                fk_rows.append({"table": table, **x})
            child_rows.extend(child_relations(conn, table))

            rows = conn.execute(
                f"SELECT * FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(SOURCE_IDS))}) "
                "ORDER BY id",
                SOURCE_IDS,
            ).fetchall()

            total_source_logs += len(rows)

            for r in rows:
                raw_rows.append(row_to_flat(table, r))

                year_id, path, note = detect_indirect_year(conn, table, r)

                # Log/audit policy mạnh khi:
                # - tên bảng kết thúc _logs
                # - không có bảng con tham chiếu đến log
                # - row có timestamp/action/message/detail hoặc tương tự
                children = child_relations(conn, table)
                time_cols = [
                    c for c in cs
                    if c.lower() in (
                        "created_at", "updated_at", "logged_at",
                        "event_time", "timestamp", "occurred_at"
                    )
                ]
                action_cols = [
                    c for c in cs
                    if any(k in c.lower() for k in (
                        "action", "event", "message", "detail",
                        "status", "note", "description"
                    ))
                ]

                looks_like_audit = (
                    table.endswith("_logs")
                    and len(children) == 0
                    and (bool(time_cols) or bool(action_cols))
                )

                if looks_like_audit:
                    proposed_policy = "KEEP_AUDIT_LOG_AT_ORIGINAL_SOURCE"
                    policy_reason = (
                        "Bảng log/audit, không có bảng con phụ thuộc; "
                        "school_id là dấu vết đơn vị tại thời điểm phát sinh."
                    )
                else:
                    proposed_policy = "REVIEW_BUSINESS_STATE"
                    policy_reason = (
                        "Chưa đủ bằng chứng coi đây là log bất biến."
                    )
                    business_state_risk += 1

                if not year_id:
                    unresolved += 1

                trace_rows.append({
                    "table": table,
                    "row_id": r["id"] if "id" in cs else "",
                    "school_id": r["school_id"],
                    "indirect_school_year_id": year_id,
                    "trace_path": path,
                    "trace_note": note,
                    "child_table_count": len(children),
                    "time_columns": ",".join(time_cols),
                    "action_detail_columns": ",".join(action_cols),
                    "looks_like_audit_log": "YES" if looks_like_audit else "NO",
                    "proposed_policy": proposed_policy,
                    "policy_reason": policy_reason,
                })

                # Dump parent FK rows để kiểm tra.
                for fk in foreign_keys(conn, table):
                    value = r[fk["from_col"]]
                    parent = fetch_parent(
                        conn, fk["ref_table"], fk["to_col"], value
                    )
                    if parent is not None:
                        flat = {
                            "source_table": table,
                            "source_row_id": r["id"] if "id" in cs else "",
                            "fk_from_col": fk["from_col"],
                            "fk_value": value,
                            "parent_table": fk["ref_table"],
                        }
                        for k in parent.keys():
                            flat["parent_" + k] = (
                                "" if parent[k] is None else parent[k]
                            )
                        parent_rows.append(flat)

        expected_total = 7
        exact_count_ok = total_source_logs == expected_total

        all_audit = all(
            r["proposed_policy"] == "KEEP_AUDIT_LOG_AT_ORIGINAL_SOURCE"
            for r in trace_rows
        )

        # Không bắt buộc mọi log phải truy được năm nếu đã chứng minh là audit log,
        # vì audit log giữ nguyên theo đơn vị tại thời điểm phát sinh.
        safe_policy = exact_count_ok and all_audit and business_state_risk == 0

        gates = [
            {
                "check": "integrity_check",
                "result": "PASS",
                "detail": integrity,
            },
            {
                "check": "exact_7_source_log_rows",
                "result": "PASS" if exact_count_ok else "FAIL",
                "detail": str(total_source_logs),
            },
            {
                "check": "all_rows_are_audit_logs",
                "result": "PASS" if all_audit else "FAIL",
                "detail": (
                    f"audit={sum(r['looks_like_audit_log']=='YES' for r in trace_rows)}"
                ),
            },
            {
                "check": "business_state_risk",
                "result": "PASS" if business_state_risk == 0 else "FAIL",
                "detail": str(business_state_risk),
            },
            {
                "check": "indirect_year_unresolved",
                "result": "INFO",
                "detail": str(unresolved),
            },
            {
                "check": "recommended_policy",
                "result": "PASS" if safe_policy else "REVIEW",
                "detail": (
                    "KEEP_AUDIT_LOG_AT_ORIGINAL_SOURCE"
                    if safe_policy
                    else "REVIEW_REQUIRED"
                ),
            },
        ]

        write_csv(
            out_dir / "210_SCHEMA_2_LOG_TABLES.csv",
            [
                "table", "cid", "name", "type",
                "notnull", "default", "pk",
            ],
            schema_rows,
        )
        write_csv(
            out_dir / "211_FOREIGN_KEYS_2_LOG_TABLES.csv",
            [
                "table", "id", "seq", "ref_table",
                "from_col", "to_col", "on_update", "on_delete",
            ],
            fk_rows,
        )
        write_csv(
            out_dir / "212_CHILD_RELATIONS_2_LOG_TABLES.csv",
            [
                "parent_table", "child_table",
                "child_from_col", "parent_to_col",
            ],
            child_rows,
        )

        raw_headers = set()
        for r in raw_rows:
            raw_headers.update(r.keys())
        write_csv(
            out_dir / "213_7_LOG_ROWS_RAW.csv",
            sorted(raw_headers) if raw_headers else ["table"],
            raw_rows,
        )

        write_csv(
            out_dir / "214_7_LOG_ROWS_TRACE_POLICY.csv",
            [
                "table", "row_id", "school_id",
                "indirect_school_year_id",
                "trace_path", "trace_note",
                "child_table_count",
                "time_columns", "action_detail_columns",
                "looks_like_audit_log",
                "proposed_policy", "policy_reason",
            ],
            trace_rows,
        )

        parent_headers = set()
        for r in parent_rows:
            parent_headers.update(r.keys())
        write_csv(
            out_dir / "215_PARENT_ROWS_OF_7_LOGS.csv",
            sorted(parent_headers) if parent_headers else [
                "source_table", "source_row_id",
                "fk_from_col", "fk_value", "parent_table"
            ],
            parent_rows,
        )

        write_csv(
            out_dir / "216_GATE_V9_2.csv",
            ["check", "result", "detail"],
            gates,
        )

        summary = out_dir / "00_TONG_QUAN_V9_1.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V9.1 - KIỂM TRA 7 LOG KHÔNG CÓ school_year_id\n"
            )
            f.write("=" * 118 + "\n")
            f.write("CHẾ ĐỘ: CHỈ ĐỌC - KHÔNG SỬA DATABASE\n")
            f.write(f"Database: {DB_PATH}\n\n")

            f.write(f"- Tổng log source: {total_source_logs}\n")
            for table in LOG_TABLES:
                n = sum(1 for r in trace_rows if r["table"] == table)
                f.write(f"- {table}: {n}\n")

            f.write(
                f"- Audit log được xác nhận theo cấu trúc: "
                f"{sum(r['looks_like_audit_log']=='YES' for r in trace_rows)}\n"
            )
            f.write(
                f"- Không truy được năm gián tiếp: {unresolved}\n"
            )
            f.write(
                f"- Business-state risk: {business_state_risk}\n\n"
            )

            f.write("CỔNG\n")
            for g in gates:
                f.write(f"- [{g['result']}] {g['check']}: {g['detail']}\n")

            f.write("\nKẾT LUẬN\n")
            f.write(
                "POLICY_2_NO_YEAR_LOG_TABLES = "
                + (
                    "KEEP_AUDIT_LOG_AT_ORIGINAL_SOURCE"
                    if safe_policy else "REVIEW_REQUIRED"
                )
                + "\n"
            )
            f.write(
                "SAFE_TO_CLOSE_V9_NO_YEAR_GAP = "
                + ("YES" if safe_policy else "NO")
                + "\n"
            )
            f.write(
                "- V9.1 không thay đổi database.\n"
            )

        zip_path = PROJECT_ROOT / f"dry_run_7_log_khong_co_nam_v9_1_{ts}.zip"
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 118)
        print("HOÀN THÀNH DRY-RUN V9.1")
        print("=" * 118)
        print(f"Tổng log source: {total_source_logs}")
        print(f"Audit log: {sum(r['looks_like_audit_log']=='YES' for r in trace_rows)}")
        print(f"Business-state risk: {business_state_risk}")
        print(
            "POLICY_2_NO_YEAR_LOG_TABLES: "
            + (
                "KEEP_AUDIT_LOG_AT_ORIGINAL_SOURCE"
                if safe_policy else "REVIEW_REQUIRED"
            )
        )
        print(
            "SAFE_TO_CLOSE_V9_NO_YEAR_GAP: "
            + ("YES" if safe_policy else "NO")
        )
        print(f"ZIP: {zip_path}")
        print("Database KHÔNG bị thay đổi.")

    finally:
        conn.close()


def main() -> None:
    try:
        main_audit()
    except AuditAbort as e:
        print()
        print("=" * 118)
        print("ĐÃ DỪNG DRY-RUN V9.1")
        print("=" * 118)
        print(str(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 118)
        print("LỖI SQLITE TRONG V9.1")
        print("=" * 118)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 118)
        print("LỖI KHÔNG DỰ KIẾN TRONG V9.1")
        print("=" * 118)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
