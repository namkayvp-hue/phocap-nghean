# -*- coding: utf-8 -*-
"""
DRY-RUN V2 - KIEM TRA SAP NHAP TRUONG THEO QD 3805/QD-UBND - NGHI LOC
=====================================================================
Muc tieu:
- CHI DOC database, KHONG SUA bat ky dong nao.
- Kiem tra sau cac bang khong co school_year_id truoc khi chuyen that.
- Truy vet khoa ngoai de tim duong lien ket toi bang co school_year_id.
- Phan loai ro: users chuyen pham vi hien tai; log giu lich su; bang nghiep vu chi
  chuyen khi xac dinh duoc lien ket an toan toi nam hoc 2026-2027.

Chay tai PowerShell:
    cd C:\\PhoCap
    .\\.venv\\Scripts\\python.exe .\\kiem_tra_sap_nhap_QD3805_Nghi_Loc_v2.py

Ket qua:
    C:\\PhoCap\\dry_run_sap_nhap_3805_Nghi_Loc_v2_<timestamp>.zip
"""

from __future__ import annotations

import csv
import os
import sqlite3
import sys
import zipfile
from collections import deque
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(r"C:\PhoCap")
DB_PATH = PROJECT_ROOT / "data" / "phocap.db"
SCHOOL_YEAR_ID = 2
SCHOOL_YEAR_LABEL = "Năm học 2026-2027"

# source_school_id -> target_school_id
MERGE_MAP = {
    750: 748,  # MN Nghi Hoa -> MN Nghi Dien
    751: 748,  # MN Nghi Van -> MN Nghi Dien
    749: 747,  # MN Nghi Trung -> MN TT Quan Hanh
    1181: 1178,  # TH Nghi Van -> TH Nghi Dien
    1180: 1179,  # TH Nghi Hoa -> TH Nghi Trung
    1608: 1605,  # THCS Nghi Van -> THCS Nghi Dien
    1607: 1606,  # THCS Nghi Hoa -> THCS Nghi Trung
}

NO_YEAR_TABLES_EXPECTED = {
    "users": "MOVE_CURRENT_SCOPE",
    "survey_investigation_participants": "TRACE_TO_2026_2027",
    "survey_investigation_team_members": "TRACE_TO_2026_2027",
    "survey_participant_submissions": "TRACE_TO_2026_2027",
    "survey_school_assignments": "TRACE_TO_2026_2027",
    "survey_team_registration_logs": "KEEP_HISTORY",
    "survey_execution_workflow_logs": "KEEP_HISTORY",
}


def die(msg: str, code: int = 1) -> None:
    print(f"\nLOI: {msg}")
    raise SystemExit(code)


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def all_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
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


def foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA foreign_key_list({qident(table)})").fetchall()
    return [
        {
            "id": r[0],
            "seq": r[1],
            "ref_table": r[2],
            "from_col": r[3],
            "to_col": r[4],
            "on_update": r[5],
            "on_delete": r[6],
            "match": r[7],
        }
        for r in rows
    ]


def has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(c["name"] == col for c in columns(conn, table))


def choose_school_column(conn: sqlite3.Connection, table: str) -> str | None:
    cols = {c["name"] for c in columns(conn, table)}
    for candidate in ("school_id", "source_school_id", "target_school_id"):
        if candidate in cols:
            return candidate
    return None


def school_name_map(conn: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(conn, "schools"):
        return {}
    cols = {c["name"] for c in columns(conn, "schools")}
    name_col = None
    for candidate in ("name", "school_name", "ten_truong"):
        if candidate in cols:
            name_col = candidate
            break
    if not name_col or "id" not in cols:
        return {}
    return {
        int(r[0]): str(r[1])
        for r in conn.execute(
            f"SELECT id, {qident(name_col)} FROM schools WHERE id IN ({','.join('?' for _ in set(MERGE_MAP) | set(MERGE_MAP.values()))})",
            tuple(set(MERGE_MAP) | set(MERGE_MAP.values())),
        ).fetchall()
    }


def build_fk_graph(conn: sqlite3.Connection, tables: list[str]):
    graph: dict[str, list[tuple[str, str, str]]] = {t: [] for t in tables}
    for t in tables:
        for fk in foreign_keys(conn, t):
            rt = fk["ref_table"]
            if rt in graph:
                # huong thuan: t.from_col -> rt.to_col
                graph[t].append((rt, fk["from_col"], fk["to_col"] or "id"))
                # huong nguoc de tim duong quan he tong quat
                graph[rt].append((t, fk["to_col"] or "id", fk["from_col"]))
    return graph


def shortest_path_to_year_table(
    conn: sqlite3.Connection, graph, start: str, max_depth: int = 5
):
    """Tim duong quan he ngan nhat tu start toi bang co school_year_id.
    Ket qua chi de phan tich schema, KHONG tu dong suy dien du lieu se chuyen.
    """
    if has_column(conn, start, "school_year_id"):
        return [(start, None, None)]

    dq = deque([(start, [(start, None, None)])])
    seen = {start}
    while dq:
        cur, path = dq.popleft()
        depth = len(path) - 1
        if depth >= max_depth:
            continue
        for nxt, cur_col, nxt_col in graph.get(cur, []):
            if nxt in seen:
                continue
            npath = path + [(nxt, cur_col, nxt_col)]
            if has_column(conn, nxt, "school_year_id"):
                return npath
            seen.add(nxt)
            dq.append((nxt, npath))
    return None


def count_by_school(conn, table: str, school_col: str, school_id: int) -> int:
    return int(
        conn.execute(
            f"SELECT COUNT(*) FROM {qident(table)} WHERE {qident(school_col)}=?",
            (school_id,),
        ).fetchone()[0]
    )


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    print("=" * 92)
    print("DRY-RUN V2 - KIEM TRA BANG KHONG CO NAM HOC - SAP NHAP QD 3805 - NGHI LOC")
    print("=" * 92)
    print(f"Database: {DB_PATH}")
    print("Che do: CHI DOC / KHONG SUA DATABASE")

    if not DB_PATH.exists():
        die(f"Khong tim thay database: {DB_PATH}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / f"dry_run_sap_nhap_3805_Nghi_Loc_v2_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row

    try:
        # Bao dam ket noi thuc su la readonly va DB hop le.
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            die(f"integrity_check khong dat: {integrity}")

        tables = all_tables(conn)
        graph = build_fk_graph(conn, tables)
        names = school_name_map(conn)

        schema_rows: list[dict] = []
        fk_rows: list[dict] = []
        classify_rows: list[dict] = []
        path_rows: list[dict] = []
        count_rows: list[dict] = []

        present = []
        absent = []

        for table, base_policy in NO_YEAR_TABLES_EXPECTED.items():
            if not table_exists(conn, table):
                absent.append(table)
                classify_rows.append({
                    "table": table,
                    "exists": "NO",
                    "school_column": "",
                    "has_school_year_id": "NO",
                    "base_policy": base_policy,
                    "recommended_policy": "SKIP_NOT_PRESENT",
                    "reason": "Bang khong ton tai trong database hien tai.",
                })
                continue

            present.append(table)
            cols = columns(conn, table)
            col_names = {c["name"] for c in cols}
            school_col = choose_school_column(conn, table)

            for c in cols:
                schema_rows.append({
                    "table": table,
                    "column": c["name"],
                    "type": c["type"],
                    "pk": c["pk"],
                    "notnull": c["notnull"],
                    "default": c["default"],
                })

            fks = foreign_keys(conn, table)
            for fk in fks:
                fk_rows.append({
                    "table": table,
                    "from_column": fk["from_col"],
                    "ref_table": fk["ref_table"],
                    "ref_column": fk["to_col"],
                    "on_update": fk["on_update"],
                    "on_delete": fk["on_delete"],
                })

            path = shortest_path_to_year_table(conn, graph, table)
            if path:
                readable = []
                for i, node in enumerate(path):
                    t, from_col, to_col = node
                    if i == 0:
                        readable.append(t)
                    else:
                        prev_t = path[i-1][0]
                        readable.append(f" -> {t}")
                path_text = "".join(readable)
                target_year_table = path[-1][0]
                found_year_path = "YES"
            else:
                path_text = ""
                target_year_table = ""
                found_year_path = "NO"

            # Chot quy tac bao thu, KHONG tu dong chuyen cac bang nghiep vu neu chua co duong nam hoc.
            if table == "users":
                rec = "MOVE_CURRENT_SCOPE"
                reason = (
                    "Tai khoan la pham vi su dung hien tai; khi truong nguon sap nhap, school_id cua user "
                    "can tro ve truong dich. Khong xoa tai khoan va khong doi username trong buoc chuyen."
                )
            elif "log" in table:
                rec = "KEEP_HISTORY"
                reason = (
                    "Bang log la dau vet lich su. Khong doi school_id hang loat de tranh lam sai lich su thao tac."
                )
            elif found_year_path == "YES":
                rec = "TRACE_AND_MOVE_2026_2027_ONLY"
                reason = (
                    f"Schema co duong quan he toi bang {target_year_table} co school_year_id; "
                    "bo chuyen that chi duoc chuyen cac dong truy vet xac nhan school_year_id=2."
                )
            else:
                rec = "HOLD_FOR_MANUAL_RULE"
                reason = (
                    "Chua tim duoc duong khoa ngoai toi bang co school_year_id; KHONG chuyen tu dong de tranh tron lich su."
                )

            classify_rows.append({
                "table": table,
                "exists": "YES",
                "school_column": school_col or "",
                "has_school_year_id": "YES" if "school_year_id" in col_names else "NO",
                "base_policy": base_policy,
                "recommended_policy": rec,
                "reason": reason,
            })

            path_rows.append({
                "table": table,
                "found_path_to_school_year": found_year_path,
                "path": path_text,
                "target_year_table": target_year_table,
                "max_depth": 5,
                "note": "Duong nay chi phan tich quan he schema; chua phai lenh chuyen du lieu.",
            })

            if school_col:
                for source_id, target_id in MERGE_MAP.items():
                    n = count_by_school(conn, table, school_col, source_id)
                    if n:
                        count_rows.append({
                            "table": table,
                            "school_column": school_col,
                            "source_school_id": source_id,
                            "source_school_name": names.get(source_id, ""),
                            "target_school_id": target_id,
                            "target_school_name": names.get(target_id, ""),
                            "rows_linked_to_source": n,
                            "recommended_policy": rec,
                        })

        # Kiem tra cac bang co school_id nhung khong co school_year_id ngoai danh sach du kien.
        extra_rows = []
        known = set(NO_YEAR_TABLES_EXPECTED)
        for t in tables:
            if t in known:
                continue
            colset = {c["name"] for c in columns(conn, t)}
            if "school_id" in colset and "school_year_id" not in colset:
                total_source_rows = 0
                for sid in MERGE_MAP:
                    try:
                        total_source_rows += count_by_school(conn, t, "school_id", sid)
                    except sqlite3.Error:
                        pass
                if total_source_rows:
                    extra_rows.append({
                        "table": t,
                        "rows_linked_to_merge_sources": total_source_rows,
                        "status": "NEW_NO_YEAR_TABLE_REQUIRES_REVIEW",
                    })

        write_csv(
            out_dir / "07_CAU_TRUC_BANG_KHONG_CO_NAM.csv",
            ["table", "column", "type", "pk", "notnull", "default"],
            schema_rows,
        )
        write_csv(
            out_dir / "08_KHOA_NGOAI_BANG_KHONG_CO_NAM.csv",
            ["table", "from_column", "ref_table", "ref_column", "on_update", "on_delete"],
            fk_rows,
        )
        write_csv(
            out_dir / "09_PHAN_LOAI_XU_LY_BANG_KHONG_CO_NAM.csv",
            ["table", "exists", "school_column", "has_school_year_id", "base_policy", "recommended_policy", "reason"],
            classify_rows,
        )
        write_csv(
            out_dir / "10_DUONG_LIEN_KET_DEN_NAM_HOC.csv",
            ["table", "found_path_to_school_year", "path", "target_year_table", "max_depth", "note"],
            path_rows,
        )
        write_csv(
            out_dir / "11_SO_DONG_THEO_TRUONG_NGUON.csv",
            ["table", "school_column", "source_school_id", "source_school_name", "target_school_id", "target_school_name", "rows_linked_to_source", "recommended_policy"],
            count_rows,
        )
        write_csv(
            out_dir / "12_BANG_KHONG_CO_NAM_PHAT_SINH_THEM.csv",
            ["table", "rows_linked_to_merge_sources", "status"],
            extra_rows,
        )

        total_linked = sum(int(r["rows_linked_to_source"]) for r in count_rows)
        users_rows = sum(
            int(r["rows_linked_to_source"]) for r in count_rows if r["table"] == "users"
        )
        keep_log_rows = sum(
            int(r["rows_linked_to_source"]) for r in count_rows if "log" in r["table"]
        )
        trace_rows = total_linked - users_rows - keep_log_rows

        summary = out_dir / "00_TONG_QUAN_V2.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write("DRY-RUN V2 - SAP NHAP TRUONG THEO QD 3805/QD-UBND - NGHI LOC\n")
            f.write("=" * 92 + "\n")
            f.write("TRANG THAI: CHI DOC / KHONG SUA DATABASE\n")
            f.write(f"Database: {DB_PATH}\n")
            f.write(f"Nam hoc muc tieu: {SCHOOL_YEAR_LABEL} (school_year_id={SCHOOL_YEAR_ID})\n")
            f.write(f"integrity_check: {integrity}\n\n")
            f.write("MUC TIEU V2\n")
            f.write("- Khoa quy tac cho cac bang khong co school_year_id.\n")
            f.write("- Truy vet khoa ngoai toi bang co school_year_id neu co.\n")
            f.write("- KHONG chuyen tu dong bang nghiep vu neu chua xac dinh duoc nam hoc.\n\n")
            f.write("PHAN LOAI AN TOAN\n")
            f.write("- users: MOVE_CURRENT_SCOPE (chuyen school_id sang truong dich; giu username/tai khoan).\n")
            f.write("- *_logs: KEEP_HISTORY (giu dau vet lich su).\n")
            f.write("- bang dieu tra/phan cong: chi chuyen dong truy vet chac chan thuoc school_year_id=2.\n\n")
            f.write("THONG KE TU DATABASE\n")
            f.write(f"- Bang du kien co mat: {len(present)}\n")
            f.write(f"- Bang du kien khong co: {len(absent)}\n")
            f.write(f"- Tong dong gan truc tiep voi truong nguon trong cac bang tren: {total_linked}\n")
            f.write(f"- Trong do users du kien chuyen pham vi: {users_rows}\n")
            f.write(f"- Dong log giu lich su: {keep_log_rows}\n")
            f.write(f"- Dong nghiep vu can truy vet nam hoc: {trace_rows}\n")
            f.write(f"- Bang khong co nam phat sinh them ngoai danh sach: {len(extra_rows)}\n\n")
            f.write("KET LUAN\n")
            if extra_rows:
                f.write("- CO bang khong co school_year_id phat sinh them. Chua du dieu kien viet bo chuyen that.\n")
            else:
                f.write("- Khong phat hien them bang school_id/khong school_year_id ngoai danh sach du kien.\n")
            unresolved = [r for r in classify_rows if r.get("recommended_policy") == "HOLD_FOR_MANUAL_RULE"]
            if unresolved:
                f.write(f"- Con {len(unresolved)} bang chua truy vet duoc nam hoc bang FK; can xem file 09 va 10.\n")
            else:
                f.write("- Tat ca bang nghiep vu da co huong xu ly/duong truy vet schema ro rang.\n")
            f.write("- DRY-RUN V2 KHONG thay doi bat ky dong du lieu nao.\n")

        zip_path = PROJECT_ROOT / f"dry_run_sap_nhap_3805_Nghi_Loc_v2_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print("\nHOAN THANH DRY-RUN V2")
        print(f"Thu muc ket qua: {out_dir}")
        print(f"File ZIP gui lai de doi chieu: {zip_path}")
        print("Khong co thay doi nao duoc ghi vao phocap.db.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
