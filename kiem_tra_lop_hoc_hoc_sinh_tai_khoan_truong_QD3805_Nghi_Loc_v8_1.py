# -*- coding: utf-8 -*-
r"""
DRY-RUN V8.1 - KIỂM TRA LỚP HỌC + HỌC SINH TẠI TÀI KHOẢN NHÀ TRƯỜNG
QĐ 3805 - NGHI LỘC
====================================================================

MỤC TIÊU
--------
- CHỈ ĐỌC database hiện tại và backup trước sáp nhập.
- KHÔNG SỬA phocap.db.
- Dò chính xác các bảng liên quan:
    + lớp học
    + học sinh
    + hồ sơ học sinh theo năm
    + quan hệ học sinh - lớp
- Tính số lượng theo từng trường nguồn / trường đích,
  đặc biệt theo góc nhìn tài khoản NHÀ TRƯỜNG.
- Xác định dữ liệu 2025-2026 cần rollover sang 2026-2027.
- Xác định khóa chống trùng.
- Xác định các bảng phụ thuộc phải đi cùng lớp/học sinh.
- Chưa ghi dữ liệu.

NGUYÊN TẮC
----------
Tại tài khoản trường đích, năm 2026-2027 phải thấy:
    dữ liệu của chính trường đích
  + dữ liệu của các trường nguồn sáp nhập vào
  - trùng
  - học sinh đã chuyển đi/nghỉ/hết phạm vi
  - dữ liệu đã có sẵn ở năm 2026-2027

Lịch sử các năm cũ giữ nguyên tại trường cũ.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_lop_hoc_hoc_sinh_tai_khoan_truong_QD3805_Nghi_Loc_v8_1.py

KẾT QUẢ
-------
    C:\PhoCap\dry_run_lop_hoc_hoc_sinh_tai_khoan_truong_QD3805_Nghi_Loc_v8_1_<timestamp>.zip
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(r"C:\PhoCap")
CURRENT_DB = PROJECT_ROOT / "data" / "phocap.db"
BACKUP_DIR = PROJECT_ROOT / "backups"

MERGE_MAP = {
    750: 748,
    751: 748,
    749: 747,
    1181: 1178,
    1180: 1179,
    1608: 1605,
    1607: 1606,
}

SOURCE_IDS = tuple(sorted(MERGE_MAP))
TARGET_IDS = tuple(sorted(set(MERGE_MAP.values())))
ALL_IDS = tuple(sorted(set(SOURCE_IDS) | set(TARGET_IDS)))


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
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    return [
        {
            "cid": r[0], "name": r[1], "type": r[2],
            "notnull": r[3], "default": r[4], "pk": r[5],
        }
        for r in rows
    ]


def colset(conn: sqlite3.Connection, table: str) -> set[str]:
    return {c["name"] for c in columns(conn, table)}


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


def unique_indexes(conn: sqlite3.Connection, table: str) -> list[dict]:
    out = []
    for r in conn.execute(f"PRAGMA index_list({qident(table)})").fetchall():
        if int(r[2]) != 1:
            continue
        idx_name = r[1]
        idx_cols = [
            x[2]
            for x in conn.execute(
                f"PRAGMA index_info({qident(idx_name)})"
            ).fetchall()
        ]
        out.append({
            "index_name": idx_name,
            "columns": ",".join(idx_cols),
        })
    return out


def find_backup() -> Path:
    candidates = sorted(
        BACKUP_DIR.glob("phocap_truoc_sap_nhap_QD3805_Nghi_Loc_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise AuditAbort(
            r"Không tìm thấy backup trước sáp nhập trong C:\PhoCap\backups."
        )
    return candidates[0]


def detect_year_ids(conn: sqlite3.Connection) -> tuple[int, int, list[dict]]:
    if not table_exists(conn, "school_years"):
        raise AuditAbort("Không có bảng school_years.")

    cs = colset(conn, "school_years")
    label_col = next(
        (c for c in ("name", "label", "school_year", "year_name") if c in cs),
        None,
    )
    if not label_col:
        raise AuditAbort("Không xác định được cột tên năm học.")

    rows = conn.execute(
        f"SELECT id, {qident(label_col)} AS label FROM school_years ORDER BY id"
    ).fetchall()

    previous = target = None
    report = []
    for r in rows:
        rid = int(r["id"])
        label = str(r["label"] or "")
        report.append({"id": rid, "label": label})
        if "2025" in label and "2026" in label:
            previous = rid
        if "2026" in label and "2027" in label:
            target = rid

    if previous is None or target is None:
        raise AuditAbort(
            f"Không xác định đủ năm học: previous={previous}, target={target}"
        )
    return previous, target, report


def school_names(conn: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(conn, "schools"):
        return {}

    cs = colset(conn, "schools")
    name_col = next(
        (c for c in ("name", "school_name", "ten_truong") if c in cs),
        None,
    )
    if not name_col:
        return {}

    rows = conn.execute(
        f"SELECT id, {qident(name_col)} FROM schools "
        f"WHERE id IN ({markers(len(ALL_IDS))})",
        ALL_IDS,
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def classify_table(table: str, cs: set[str], fks: list[dict]) -> tuple[str, int, list[str]]:
    """
    Phân loại sơ bộ:
      CLASS
      STUDENT_MASTER
      STUDENT_YEAR
      ENROLLMENT
      OTHER_RELATED
    """
    low = table.lower()
    reasons = []
    scores = defaultdict(int)

    if any(x in low for x in ("class", "classes", "lop", "classroom")):
        scores["CLASS"] += 5
        reasons.append("Tên bảng gợi ý lớp")

    if any(x in low for x in ("student", "students", "hoc_sinh", "pupil", "learner")):
        scores["STUDENT_MASTER"] += 4
        scores["STUDENT_YEAR"] += 4
        reasons.append("Tên bảng gợi ý học sinh")

    if any(x in low for x in ("enrollment", "enrol", "class_student", "student_class")):
        scores["ENROLLMENT"] += 6
        reasons.append("Tên bảng gợi ý quan hệ HS-lớp")

    if "school_id" in cs:
        scores["CLASS"] += 2
        scores["STUDENT_YEAR"] += 2
        scores["ENROLLMENT"] += 1
        reasons.append("Có school_id")

    if "school_year_id" in cs:
        scores["CLASS"] += 3
        scores["STUDENT_YEAR"] += 4
        scores["ENROLLMENT"] += 3
        reasons.append("Có school_year_id")

    if "class_id" in cs:
        scores["STUDENT_YEAR"] += 2
        scores["ENROLLMENT"] += 4
        reasons.append("Có class_id")

    if any(c in cs for c in ("student_id", "student_member_id", "pupil_id")):
        scores["STUDENT_YEAR"] += 3
        scores["ENROLLMENT"] += 4
        reasons.append("Có khóa học sinh")

    if any(c in cs for c in ("class_name", "class_code", "grade", "grade_level")):
        scores["CLASS"] += 4
        reasons.append("Có cột mô tả lớp")

    if any(c in cs for c in ("full_name", "student_code", "date_of_birth")):
        scores["STUDENT_MASTER"] += 4
        reasons.append("Có thông tin học sinh")

    for fk in fks:
        ref = fk["ref_table"].lower()
        if any(x in ref for x in ("class", "lop")):
            scores["ENROLLMENT"] += 2
            scores["STUDENT_YEAR"] += 2
            reasons.append(f"FK tới lớp: {fk['from_col']}->{fk['ref_table']}")
        if any(x in ref for x in ("student", "hoc_sinh", "pupil")):
            scores["ENROLLMENT"] += 2
            scores["STUDENT_YEAR"] += 1
            reasons.append(f"FK tới học sinh: {fk['from_col']}->{fk['ref_table']}")

    if not scores:
        return "OTHER_RELATED", 0, reasons

    kind, score = max(scores.items(), key=lambda x: x[1])
    return kind, score, reasons


def count_rows(
    conn: sqlite3.Connection,
    table: str,
    previous_year_id: int,
    target_year_id: int,
    names: dict[int, str],
) -> list[dict]:
    cs = colset(conn, table)
    out = []

    if "school_id" not in cs:
        return out

    has_year = "school_year_id" in cs

    for sid in ALL_IDS:
        if has_year:
            prev = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                "WHERE school_id=? AND school_year_id=?",
                (sid, previous_year_id),
            ).fetchone()[0]
            curr = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                "WHERE school_id=? AND school_year_id=?",
                (sid, target_year_id),
            ).fetchone()[0]
        else:
            prev = ""
            curr = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} WHERE school_id=?",
                (sid,),
            ).fetchone()[0]

        if prev or curr:
            out.append({
                "table": table,
                "school_id": sid,
                "school_name": names.get(sid, ""),
                "merger_role": "SOURCE" if sid in SOURCE_IDS else "TARGET",
                "previous_year_rows": prev,
                "target_or_current_rows": curr,
                "has_school_year_id": "YES" if has_year else "NO",
            })
    return out


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


def key_candidates(cs: set[str], uniques: list[dict]) -> str:
    preferred = [
        c for c in (
            "student_id", "student_member_id", "student_code",
            "class_id", "class_code", "class_name",
            "school_id", "school_year_id"
        )
        if c in cs
    ]
    for u in uniques:
        preferred.append("UNIQUE(" + u["columns"] + ")")
    return " | ".join(preferred)


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def audit() -> None:
    print("=" * 114)
    print("DRY-RUN V8.1 - LỚP HỌC + HỌC SINH TẠI TÀI KHOẢN NHÀ TRƯỜNG")
    print("=" * 114)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not CURRENT_DB.exists():
        raise AuditAbort(f"Không tìm thấy current DB: {CURRENT_DB}")

    backup_db = find_backup()
    cur = connect_ro(CURRENT_DB)
    bak = connect_ro(backup_db)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / (
        f"dry_run_lop_hoc_hoc_sinh_tai_khoan_truong_QD3805_Nghi_Loc_v8_1_{ts}"
    )
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        int_cur = cur.execute("PRAGMA integrity_check").fetchone()[0]
        int_bak = bak.execute("PRAGMA integrity_check").fetchone()[0]
        if int_cur != "ok":
            raise AuditAbort(f"Current DB integrity_check={int_cur}")
        if int_bak != "ok":
            raise AuditAbort(f"Backup DB integrity_check={int_bak}")

        previous_year_id, target_year_id, years = detect_year_ids(cur)
        names = school_names(cur)

        candidate_tables = []
        schemas = []
        fks_all = []
        uniques_all = []
        counts_all = []
        relations_all = []

        for table in all_tables(cur):
            cs = colset(cur, table)
            fks = foreign_keys(cur, table)
            uniques = unique_indexes(cur, table)
            kind, score, reasons = classify_table(table, cs, fks)

            # Chỉ giữ bảng đủ liên quan.
            if score < 4:
                continue

            candidate_tables.append({
                "table": table,
                "kind": kind,
                "score": score,
                "has_school_id": "YES" if "school_id" in cs else "NO",
                "has_school_year_id": "YES" if "school_year_id" in cs else "NO",
                "key_candidates": key_candidates(cs, uniques),
                "reasons": " | ".join(reasons),
            })

            for c in columns(cur, table):
                schemas.append({"table": table, **c})

            for fk in fks:
                fks_all.append({"table": table, **fk})

            for u in uniques:
                uniques_all.append({"table": table, **u})

            counts_all.extend(
                count_rows(
                    cur, table,
                    previous_year_id, target_year_id,
                    names
                )
            )

            relations_all.extend(child_relations(cur, table))

        candidate_tables.sort(
            key=lambda x: (
                {"CLASS": 0, "STUDENT_MASTER": 1, "STUDENT_YEAR": 2, "ENROLLMENT": 3}.get(x["kind"], 9),
                -x["score"],
                x["table"],
            )
        )

        top_by_kind = {}
        for kind in ("CLASS", "STUDENT_MASTER", "STUDENT_YEAR", "ENROLLMENT"):
            rows = [x for x in candidate_tables if x["kind"] == kind]
            if not rows:
                continue
            max_score = max(x["score"] for x in rows)
            top = [x for x in rows if x["score"] == max_score]
            if len(top) == 1:
                top_by_kind[kind] = top[0]["table"]

        # Tổng hợp theo target dưới góc nhìn tài khoản trường.
        target_scope = []
        for tid in TARGET_IDS:
            sources = sorted([sid for sid, t in MERGE_MAP.items() if t == tid])
            target_scope.append({
                "target_school_id": tid,
                "target_school_name": names.get(tid, ""),
                "merged_source_ids": ",".join(map(str, sources)),
                "merged_source_names": " | ".join(names.get(s, "") for s in sources),
                "school_account_scope_rule": (
                    "Tài khoản trường chỉ thấy dữ liệu school_id của trường đích "
                    "ở năm hiện hành; dữ liệu nguồn phải được rollover/gộp về target."
                ),
            })

        gate = [
            {
                "check": "current_integrity_check",
                "result": "PASS" if int_cur == "ok" else "FAIL",
                "detail": str(int_cur),
            },
            {
                "check": "backup_integrity_check",
                "result": "PASS" if int_bak == "ok" else "FAIL",
                "detail": str(int_bak),
            },
            {
                "check": "years_identified",
                "result": "PASS",
                "detail": f"previous={previous_year_id}; target={target_year_id}",
            },
            {
                "check": "class_table_identified",
                "result": "PASS" if "CLASS" in top_by_kind else "REVIEW",
                "detail": top_by_kind.get("CLASS", "Cần xem candidate list"),
            },
            {
                "check": "student_table_identified",
                "result": "PASS" if (
                    "STUDENT_YEAR" in top_by_kind or "STUDENT_MASTER" in top_by_kind
                ) else "REVIEW",
                "detail": (
                    top_by_kind.get("STUDENT_YEAR")
                    or top_by_kind.get("STUDENT_MASTER")
                    or "Cần xem candidate list"
                ),
            },
        ]

        ready = (
            gate[0]["result"] == "PASS"
            and gate[1]["result"] == "PASS"
            and gate[2]["result"] == "PASS"
            and gate[3]["result"] == "PASS"
            and gate[4]["result"] == "PASS"
        )

        write_csv(
            out_dir / "130_SCHOOL_YEARS.csv",
            ["id", "label"],
            years,
        )
        write_csv(
            out_dir / "131_CANDIDATE_TABLES.csv",
            [
                "table", "kind", "score",
                "has_school_id", "has_school_year_id",
                "key_candidates", "reasons",
            ],
            candidate_tables,
        )
        write_csv(
            out_dir / "132_SCHEMA_CANDIDATES.csv",
            [
                "table", "cid", "name", "type",
                "notnull", "default", "pk",
            ],
            schemas,
        )
        write_csv(
            out_dir / "133_FOREIGN_KEYS.csv",
            [
                "table", "id", "seq", "ref_table",
                "from_col", "to_col", "on_update", "on_delete",
            ],
            fks_all,
        )
        write_csv(
            out_dir / "134_UNIQUE_INDEXES.csv",
            ["table", "index_name", "columns"],
            uniques_all,
        )
        write_csv(
            out_dir / "135_COUNTS_THEO_TRUONG_NAM.csv",
            [
                "table", "school_id", "school_name",
                "merger_role", "previous_year_rows",
                "target_or_current_rows", "has_school_year_id",
            ],
            counts_all,
        )
        write_csv(
            out_dir / "136_CHILD_RELATIONS.csv",
            [
                "parent_table", "child_table",
                "child_from_col", "parent_to_col",
            ],
            relations_all,
        )
        write_csv(
            out_dir / "137_PHAM_VI_TAI_KHOAN_TRUONG_SAU_SAP_NHAP.csv",
            [
                "target_school_id", "target_school_name",
                "merged_source_ids", "merged_source_names",
                "school_account_scope_rule",
            ],
            target_scope,
        )
        write_csv(
            out_dir / "138_GATE_V8_2.csv",
            ["check", "result", "detail"],
            gate,
        )

        summary = out_dir / "00_TONG_QUAN_V8_1.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V8.1 - LỚP HỌC + HỌC SINH TẠI TÀI KHOẢN NHÀ TRƯỜNG\n"
            )
            f.write("=" * 114 + "\n")
            f.write("CHẾ ĐỘ: CHỈ ĐỌC - KHÔNG SỬA DATABASE\n")
            f.write(f"Current DB: {CURRENT_DB}\n")
            f.write(f"Backup DB : {backup_db}\n")
            f.write(f"Năm trước: {previous_year_id}\n")
            f.write(f"Năm hiện hành: {target_year_id}\n\n")

            f.write("BẢNG ỨNG VIÊN CHÍNH\n")
            for kind in ("CLASS", "STUDENT_MASTER", "STUDENT_YEAR", "ENROLLMENT"):
                f.write(f"- {kind}: {top_by_kind.get(kind, 'CẦN XEM THÊM')}\n")

            f.write("\nPHẠM VI TÀI KHOẢN TRƯỜNG\n")
            for r in target_scope:
                f.write(
                    f"- {r['target_school_name']} ({r['target_school_id']}): "
                    f"nhận nguồn [{r['merged_source_ids']}].\n"
                )

            f.write("\nCỔNG V8.2\n")
            for g in gate:
                f.write(f"- [{g['result']}] {g['check']}: {g['detail']}\n")

            f.write("\nKẾT LUẬN\n")
            f.write(f"READY_FOR_V8_2 = {'YES' if ready else 'NO'}\n")
            f.write("- V8.1 KHÔNG thay đổi database.\n")

        zip_path = PROJECT_ROOT / (
            f"dry_run_lop_hoc_hoc_sinh_tai_khoan_truong_QD3805_Nghi_Loc_v8_1_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 114)
        print("HOÀN THÀNH DRY-RUN V8.1")
        print("=" * 114)
        print(f"CLASS: {top_by_kind.get('CLASS', 'CẦN XEM THÊM')}")
        print(f"STUDENT_MASTER: {top_by_kind.get('STUDENT_MASTER', 'CẦN XEM THÊM')}")
        print(f"STUDENT_YEAR: {top_by_kind.get('STUDENT_YEAR', 'CẦN XEM THÊM')}")
        print(f"ENROLLMENT: {top_by_kind.get('ENROLLMENT', 'CẦN XEM THÊM')}")
        print(f"READY_FOR_V8_2: {'YES' if ready else 'NO'}")
        print(f"ZIP: {zip_path}")
        print("Database KHÔNG bị thay đổi.")

    finally:
        cur.close()
        bak.close()


def main() -> None:
    try:
        audit()
    except AuditAbort as e:
        print()
        print("=" * 114)
        print("ĐÃ DỪNG DRY-RUN V8.1")
        print("=" * 114)
        print(str(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 114)
        print("LỖI SQLITE TRONG V8.1")
        print("=" * 114)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 114)
        print("LỖI KHÔNG DỰ KIẾN TRONG V8.1")
        print("=" * 114)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
