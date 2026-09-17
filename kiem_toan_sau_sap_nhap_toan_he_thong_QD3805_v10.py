# -*- coding: utf-8 -*-
r"""
DRY-RUN V10 - KIỂM TOÁN SAU SÁP NHẬP TOÀN HỆ THỐNG QĐ 3805
=============================================================

MỤC TIÊU
--------
Kiểm tra toàn bộ trạng thái sau sáp nhập QĐ 3805 trên database hiện tại:

1. Trường nguồn đã khóa, trường đích đang hoạt động.
2. Tài khoản:
   - tài khoản Trường nguồn còn ở trường nguồn nhưng đã khóa;
   - CBQL/GV/NV không còn active tại trường nguồn;
   - tài khoản/truy cập trường đích vẫn hoạt động.
3. Đội ngũ staff_year_records:
   - năm hiện hành không còn row tại trường nguồn;
   - lịch sử năm cũ vẫn giữ tại trường nguồn;
   - trường đích có dữ liệu hiện hành.
4. Lớp học:
   - năm hiện hành không còn lớp tại nguồn;
   - lịch sử giữ nguyên;
   - lớp hiện hành ở đích.
5. Học sinh/enrollment:
   - students là master, không ép đổi trường;
   - student_enrollments năm hiện hành không còn tại nguồn;
   - lịch sử giữ nguyên.
6. Điều tra:
   - bảng theo năm không còn row hiện hành ở nguồn;
   - bảng nghiệp vụ không có school_year_id đã chuyển đúng nếu cần;
   - audit log được phép giữ tại nguồn.
7. CSVC / báo cáo / dữ liệu nghiệp vụ khác:
   - mọi bảng có school_id + school_year_id không còn row năm hiện hành tại nguồn;
   - lịch sử vẫn giữ nguyên.
8. Kiểm tra toàn bộ bảng có school_id nhưng không có school_year_id.
9. PRAGMA foreign_key_check + integrity_check.
10. Tổng hợp số liệu mà tài khoản trường đích hiện có thể nhìn thấy theo năm hiện hành.

V10 CHỈ ĐỌC:
- KHÔNG sửa database.
- KHÔNG sửa file phương án.
- KHÔNG sửa mã nguồn.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_toan_sau_sap_nhap_toan_he_thong_QD3805_v10.py

KẾT QUẢ
-------
    C:\PhoCap\dry_run_kiem_toan_sau_sap_nhap_QD3805_v10_<timestamp>.zip
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"

AUDIT_LOG_TABLES = {
    "survey_execution_workflow_logs",
    "survey_team_registration_logs",
}

SPECIAL_NO_YEAR_TABLES = {
    "users",
}

EXPECTED_QD3805_PLAN_COUNT = 6


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def all_tables(con: sqlite3.Connection) -> list[str]:
    return [
        str(r[0])
        for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def columns(con: sqlite3.Connection, table: str) -> list[dict]:
    rows = con.execute(f"PRAGMA table_info({qident(table)})").fetchall()
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


def colset(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(x["name"]) for x in columns(con, table)}


def normalize(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        ch for ch in text if unicodedata.category(ch) != "Mn"
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def scalar(con: sqlite3.Connection, sql: str, params=()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def load_qd3805_plans() -> tuple[dict, list[dict]]:
    if not PLAN_FILE.exists():
        raise AuditAbort(f"Không tìm thấy file phương án: {PLAN_FILE}")

    try:
        payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AuditAbort(f"Không đọc được file phương án: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("plans"), list):
        raise AuditAbort("File phương án không đúng cấu trúc {version, plans:[...]}.")

    plans = []
    for raw in payload["plans"]:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or "")
        doc = str(raw.get("document_code") or "")
        if not (pid.startswith("QD3805-") or "3805" in doc):
            continue

        item = dict(raw)
        for key in ("school_year_id", "commune_id", "target_school_id"):
            try:
                item[key] = int(item.get(key))
            except (TypeError, ValueError):
                item[key] = None

        src = []
        for value in item.get("source_school_ids") or []:
            try:
                sid = int(value)
            except (TypeError, ValueError):
                continue
            if sid not in src:
                src.append(sid)
        item["source_school_ids"] = sorted(src)
        item["status"] = str(item.get("status") or "").upper()
        plans.append(item)

    if not plans:
        raise AuditAbort("Không tìm thấy phương án QĐ 3805.")

    return payload, plans


def school_year_labels(con: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(con, "school_years"):
        return {}
    cs = colset(con, "school_years")
    label_col = next(
        (c for c in ("name", "label", "school_year", "year_name") if c in cs),
        None,
    )
    if not label_col:
        return {}
    rows = con.execute(
        f"SELECT id,{qident(label_col)} AS label FROM school_years ORDER BY id"
    ).fetchall()
    return {int(r["id"]): str(r["label"] or "") for r in rows}


def school_map(con: sqlite3.Connection, ids: list[int]) -> dict[int, dict]:
    if not table_exists(con, "schools"):
        raise AuditAbort("Không có bảng schools.")

    cs = colset(con, "schools")
    name_col = next(
        (c for c in ("name", "school_name", "ten_truong") if c in cs),
        None,
    )
    code_col = next(
        (c for c in ("code", "school_code", "ma_truong") if c in cs),
        None,
    )
    if not name_col:
        raise AuditAbort("Không xác định được cột tên trường.")

    select = [
        "id",
        f"{qident(name_col)} AS name",
        "commune_id" if "commune_id" in cs else "NULL AS commune_id",
        "is_active" if "is_active" in cs else "NULL AS is_active",
    ]
    if code_col:
        select.append(f"{qident(code_col)} AS code")
    else:
        select.append("'' AS code")

    rows = con.execute(
        "SELECT " + ",".join(select)
        + f" FROM schools WHERE id IN ({markers(len(ids))})",
        ids,
    ).fetchall()

    return {
        int(r["id"]): {
            "id": int(r["id"]),
            "name": str(r["name"] or ""),
            "code": str(r["code"] or ""),
            "commune_id": r["commune_id"],
            "is_active": r["is_active"],
        }
        for r in rows
    }


def commune_map(con: sqlite3.Connection, ids: list[int]) -> dict[int, dict]:
    if not ids or not table_exists(con, "communes"):
        return {}
    cs = colset(con, "communes")
    name_col = next(
        (c for c in ("name", "commune_name", "ten_xa") if c in cs),
        None,
    )
    if not name_col:
        return {}
    rows = con.execute(
        f"SELECT id,{qident(name_col)} AS name FROM communes "
        f"WHERE id IN ({markers(len(ids))})",
        ids,
    ).fetchall()
    return {
        int(r["id"]): {"id": int(r["id"]), "name": str(r["name"] or "")}
        for r in rows
    }


def category_for_table(table: str) -> str:
    low = table.lower()

    if table == "users":
        return "TAI_KHOAN"

    if (
        "staff" in low
        or "teacher" in low
        or "employee" in low
        or "personnel" in low
    ):
        return "DOI_NGU"

    if (
        low == "classes"
        or "class_" in low
        or low.startswith("class")
    ):
        return "LOP_HOC"

    if (
        "student" in low
        or "enrollment" in low
        or "pupil" in low
    ):
        return "HOC_SINH"

    if low.startswith("survey_") or "investigation" in low:
        return "DIEU_TRA"

    if (
        "csvc" in low
        or "facility" in low
        or "facilities" in low
        or "infrastructure" in low
        or "classroom" in low
        or "sanitation" in low
        or "equipment" in low
        or "playground" in low
    ):
        return "CSVC"

    if "report" in low or "summary" in low or "statistic" in low:
        return "BAO_CAO"

    return "NGHIEP_VU_KHAC"


def table_policy(table: str, cs: set[str]) -> str:
    if table == "students":
        return "MASTER_KEEP"
    if table == "users":
        return "USERS_SPECIAL"
    if table in AUDIT_LOG_TABLES:
        return "AUDIT_LOG_KEEP_SOURCE"
    if {"school_id", "school_year_id"} <= cs:
        return "CURRENT_YEAR_MUST_LEAVE_SOURCE_HISTORY_STAYS"
    if "school_id" in cs:
        return "NO_YEAR_REVIEW"
    return "NO_SCHOOL_SCOPE"


def user_kind(username: str) -> str:
    name = str(username or "")
    if name.startswith("truong_"):
        return "SCHOOL_LOGIN"
    if name.startswith("cbql."):
        return "CBQL"
    if name.startswith("gv."):
        return "GIAO_VIEN"
    return "OTHER"


def plan_school_rows(
    plans: list[dict],
    schools: dict[int, dict],
    communes: dict[int, dict],
) -> list[dict]:
    rows = []
    for p in plans:
        target_id = p["target_school_id"]
        target = schools.get(target_id, {})
        rows.append({
            "plan_id": p.get("id", ""),
            "role": "TARGET",
            "school_id": target_id,
            "school_name": target.get("name", ""),
            "school_code": target.get("code", ""),
            "commune_id": target.get("commune_id", ""),
            "commune_name": communes.get(
                int(target.get("commune_id"))
                if target.get("commune_id") is not None else -1,
                {},
            ).get("name", ""),
            "is_active": target.get("is_active", ""),
            "expected_active": 1,
            "status_check": (
                "PASS" if target.get("is_active") in (1, True) else "FAIL"
            ),
        })
        for sid in p["source_school_ids"]:
            source = schools.get(sid, {})
            rows.append({
                "plan_id": p.get("id", ""),
                "role": "SOURCE",
                "school_id": sid,
                "school_name": source.get("name", ""),
                "school_code": source.get("code", ""),
                "commune_id": source.get("commune_id", ""),
                "commune_name": communes.get(
                    int(source.get("commune_id"))
                    if source.get("commune_id") is not None else -1,
                    {},
                ).get("name", ""),
                "is_active": source.get("is_active", ""),
                "expected_active": 0,
                "status_check": (
                    "PASS" if source.get("is_active") in (0, False) else "FAIL"
                ),
            })
    return rows


def user_audit(
    con: sqlite3.Connection,
    source_ids: list[int],
    target_ids: list[int],
    schools: dict[int, dict],
) -> tuple[list[dict], list[dict], list[str]]:
    source_rows = []
    target_summary = []
    problems = []

    if not table_exists(con, "users"):
        problems.append("Không có bảng users.")
        return source_rows, target_summary, problems

    cs = colset(con, "users")
    required = {"id", "username", "school_id", "is_active"}
    if not required <= cs:
        problems.append(
            "Bảng users thiếu cột bắt buộc: "
            + ",".join(sorted(required - cs))
        )
        return source_rows, target_summary, problems

    rows = con.execute(
        f"SELECT id,username,full_name,role_id,school_id,is_active "
        f"FROM users WHERE school_id IN ({markers(len(source_ids))}) "
        "ORDER BY school_id,id",
        source_ids,
    ).fetchall()

    for r in rows:
        kind = user_kind(r["username"])
        ok = (
            kind == "SCHOOL_LOGIN"
            and r["is_active"] in (0, False)
        )
        if not ok:
            problems.append(
                f"User source bất thường id={r['id']} "
                f"username={r['username']} school_id={r['school_id']} "
                f"kind={kind} active={r['is_active']}"
            )
        source_rows.append({
            "id": r["id"],
            "username": r["username"],
            "full_name": r["full_name"],
            "role_id": r["role_id"],
            "school_id": r["school_id"],
            "school_name": schools.get(int(r["school_id"]), {}).get("name", ""),
            "is_active": r["is_active"],
            "kind": kind,
            "expected": "Chỉ SCHOOL_LOGIN đã khóa được phép còn tại nguồn",
            "check": "PASS" if ok else "FAIL",
        })

    for tid in target_ids:
        counts = defaultdict(int)
        active_counts = defaultdict(int)
        trows = con.execute(
            "SELECT username,is_active FROM users WHERE school_id=?",
            (tid,),
        ).fetchall()
        for r in trows:
            kind = user_kind(r["username"])
            counts[kind] += 1
            if r["is_active"] in (1, True):
                active_counts[kind] += 1

        target_summary.append({
            "target_school_id": tid,
            "target_school_name": schools.get(tid, {}).get("name", ""),
            "total_users": len(trows),
            "school_login_total": counts["SCHOOL_LOGIN"],
            "school_login_active": active_counts["SCHOOL_LOGIN"],
            "cbql_total": counts["CBQL"],
            "cbql_active": active_counts["CBQL"],
            "teacher_total": counts["GIAO_VIEN"],
            "teacher_active": active_counts["GIAO_VIEN"],
            "other_total": counts["OTHER"],
            "other_active": active_counts["OTHER"],
        })

        if active_counts["SCHOOL_LOGIN"] < 1:
            problems.append(
                f"Trường đích {tid} không có tài khoản Trường active."
            )

    return source_rows, target_summary, problems


def direct_year_audit(
    con: sqlite3.Connection,
    tables: list[str],
    source_ids: list[int],
    target_ids: list[int],
    current_year_id: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    residuals = []
    historical = []
    target_current = []

    for table in tables:
        cs = colset(con, table)
        if not {"school_id", "school_year_id"} <= cs:
            continue

        category = category_for_table(table)

        src_current = scalar(
            con,
            f"SELECT COUNT(*) FROM {qident(table)} "
            f"WHERE school_id IN ({markers(len(source_ids))}) "
            "AND school_year_id=?",
            source_ids + [current_year_id],
        )
        src_history = scalar(
            con,
            f"SELECT COUNT(*) FROM {qident(table)} "
            f"WHERE school_id IN ({markers(len(source_ids))}) "
            "AND school_year_id<>?",
            source_ids + [current_year_id],
        )
        tgt_current = scalar(
            con,
            f"SELECT COUNT(*) FROM {qident(table)} "
            f"WHERE school_id IN ({markers(len(target_ids))}) "
            "AND school_year_id=?",
            target_ids + [current_year_id],
        )

        residuals.append({
            "table": table,
            "category": category,
            "source_current_year_rows": src_current,
            "expected": 0,
            "check": "PASS" if src_current == 0 else "FAIL",
        })

        historical.append({
            "table": table,
            "category": category,
            "source_historical_rows": src_history,
            "policy": "GIỮ NGUYÊN TẠI TRƯỜNG NGUỒN",
        })

        target_current.append({
            "table": table,
            "category": category,
            "target_current_year_rows": tgt_current,
        })

    return residuals, historical, target_current


def no_year_audit(
    con: sqlite3.Connection,
    tables: list[str],
    source_ids: list[int],
) -> tuple[list[dict], list[str]]:
    rows = []
    problems = []

    for table in tables:
        cs = colset(con, table)
        if "school_id" not in cs or "school_year_id" in cs:
            continue

        count = scalar(
            con,
            f"SELECT COUNT(*) FROM {qident(table)} "
            f"WHERE school_id IN ({markers(len(source_ids))})",
            source_ids,
        )
        if count == 0:
            continue

        if table == "users":
            policy = "USERS_SPECIAL"
            result = "INFO"
            detail = "Chỉ tài khoản Trường nguồn đã khóa được phép còn."
        elif table in AUDIT_LOG_TABLES:
            policy = "AUDIT_LOG_KEEP_SOURCE"
            result = "PASS"
            detail = "Audit log giữ tại đơn vị phát sinh."
        else:
            policy = "NO_YEAR_REVIEW"
            result = "REVIEW"
            detail = "Có school_id nhưng không có school_year_id; cần xác nhận policy."
            problems.append(
                f"Bảng no-year còn row tại nguồn cần review: {table}={count}"
            )

        rows.append({
            "table": table,
            "category": category_for_table(table),
            "source_rows": count,
            "policy": policy,
            "result": result,
            "detail": detail,
        })

    return rows, problems


def key_table_by_plan(
    con: sqlite3.Connection,
    plans: list[dict],
    schools: dict[int, dict],
    current_year_id: int,
) -> list[dict]:
    key_tables = [
        "staff_year_records",
        "classes",
        "student_enrollments",
        "survey_person_year_records",
    ]
    rows = []

    for p in plans:
        tid = p["target_school_id"]
        srcs = p["source_school_ids"]

        for table in key_tables:
            if not table_exists(con, table):
                continue
            cs = colset(con, table)
            if not {"school_id", "school_year_id"} <= cs:
                continue

            src_current = scalar(
                con,
                f"SELECT COUNT(*) FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(srcs))}) "
                "AND school_year_id=?",
                srcs + [current_year_id],
            )
            src_history = scalar(
                con,
                f"SELECT COUNT(*) FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(srcs))}) "
                "AND school_year_id<>?",
                srcs + [current_year_id],
            )
            tgt_current = scalar(
                con,
                f"SELECT COUNT(*) FROM {qident(table)} "
                "WHERE school_id=? AND school_year_id=?",
                (tid, current_year_id),
            )

            rows.append({
                "plan_id": p.get("id", ""),
                "table": table,
                "category": category_for_table(table),
                "source_ids": ",".join(map(str, srcs)),
                "target_id": tid,
                "target_name": schools.get(tid, {}).get("name", ""),
                "source_current_year_rows": src_current,
                "source_historical_rows": src_history,
                "target_current_year_rows": tgt_current,
                "current_source_check": "PASS" if src_current == 0 else "FAIL",
            })

    return rows


def target_visible_summary(
    target_current_rows: list[dict],
    target_user_summary: list[dict],
) -> list[dict]:
    grouped = defaultdict(int)
    for r in target_current_rows:
        grouped[r["category"]] += int(r["target_current_year_rows"])

    total_target_users = sum(int(r["total_users"]) for r in target_user_summary)

    order = [
        ("TAI_KHOAN", total_target_users),
        ("DOI_NGU", grouped["DOI_NGU"]),
        ("LOP_HOC", grouped["LOP_HOC"]),
        ("HOC_SINH", grouped["HOC_SINH"]),
        ("DIEU_TRA", grouped["DIEU_TRA"]),
        ("CSVC", grouped["CSVC"]),
        ("BAO_CAO", grouped["BAO_CAO"]),
        ("NGHIEP_VU_KHAC", grouped["NGHIEP_VU_KHAC"]),
    ]
    return [
        {
            "data_group": name,
            "current_rows_at_targets": value,
            "note": (
                "users không có school_year_id"
                if name == "TAI_KHOAN"
                else "Tổng các bảng có school_id + school_year_id"
            ),
        }
        for name, value in order
    ]


def main() -> None:
    print("=" * 120)
    print("DRY-RUN V10 - KIỂM TOÁN SAU SÁP NHẬP TOÀN HỆ THỐNG QĐ 3805")
    print("=" * 120)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE / JSON / MÃ NGUỒN")

    if not DB_PATH.exists():
        raise AuditAbort(f"Không tìm thấy database: {DB_PATH}")

    _, plans = load_qd3805_plans()

    if len(plans) != EXPECTED_QD3805_PLAN_COUNT:
        raise AuditAbort(
            f"QĐ 3805 phải có {EXPECTED_QD3805_PLAN_COUNT} nhóm, "
            f"hiện tìm thấy {len(plans)}."
        )

    year_ids = {p.get("school_year_id") for p in plans}
    if len(year_ids) != 1 or None in year_ids:
        raise AuditAbort(
            "Các nhóm QĐ 3805 không có một school_year_id duy nhất."
        )
    current_year_id = next(iter(year_ids))

    source_ids = sorted({
        sid
        for p in plans
        for sid in p["source_school_ids"]
    })
    target_ids = sorted({
        int(p["target_school_id"])
        for p in plans
        if p.get("target_school_id") is not None
    })
    all_school_ids = sorted(set(source_ids) | set(target_ids))

    con = connect_ro(DB_PATH)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"dry_run_kiem_toan_sau_sap_nhap_QD3805_v10_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_rows_raw = con.execute("PRAGMA foreign_key_check").fetchall()

        years = school_year_labels(con)
        schools = school_map(con, all_school_ids)
        commune_ids = sorted({
            int(s["commune_id"])
            for s in schools.values()
            if s.get("commune_id") is not None
        })
        communes = commune_map(con, commune_ids)

        if len(schools) != len(all_school_ids):
            missing = sorted(set(all_school_ids) - set(schools))
            raise AuditAbort(f"Không tìm thấy school_id: {missing}")

        plan_rows = []
        for p in plans:
            plan_rows.append({
                "plan_id": p.get("id", ""),
                "document_code": p.get("document_code", ""),
                "school_year_id": current_year_id,
                "school_year_label": years.get(current_year_id, ""),
                "commune_id": p.get("commune_id", ""),
                "commune_name": communes.get(
                    int(p["commune_id"])
                    if p.get("commune_id") is not None else -1,
                    {},
                ).get("name", ""),
                "level_code": p.get("level_code", ""),
                "source_school_ids": ",".join(map(str, p["source_school_ids"])),
                "source_school_names": " | ".join(
                    schools[sid]["name"] for sid in p["source_school_ids"]
                ),
                "target_school_id": p["target_school_id"],
                "target_school_name": schools[p["target_school_id"]]["name"],
                "status": p.get("status", ""),
            })

        school_status_rows = plan_school_rows(
            plans, schools, communes
        )

        source_user_rows, target_user_summary, user_problems = user_audit(
            con, source_ids, target_ids, schools
        )

        tables = all_tables(con)
        direct_residuals, historical_rows, target_current_rows = direct_year_audit(
            con,
            tables,
            source_ids,
            target_ids,
            current_year_id,
        )

        no_year_rows, no_year_problems = no_year_audit(
            con,
            tables,
            source_ids,
        )

        key_plan_rows = key_table_by_plan(
            con,
            plans,
            schools,
            current_year_id,
        )

        visible_rows = target_visible_summary(
            target_current_rows,
            target_user_summary,
        )

        table_policy_rows = []
        for table in tables:
            cs = colset(con, table)
            if "school_id" not in cs and table != "students":
                continue
            table_policy_rows.append({
                "table": table,
                "category": category_for_table(table),
                "has_school_id": "YES" if "school_id" in cs else "NO",
                "has_school_year_id": "YES" if "school_year_id" in cs else "NO",
                "policy": table_policy(table, cs),
            })

        # FK report.
        fk_rows = []
        for r in fk_rows_raw:
            fk_rows.append({
                "table": r[0],
                "rowid": r[1],
                "parent": r[2],
                "fk_index": r[3],
            })

        # Gates.
        school_failures = [
            r for r in school_status_rows if r["status_check"] != "PASS"
        ]
        direct_failures = [
            r for r in direct_residuals if r["check"] != "PASS"
        ]
        key_failures = [
            r for r in key_plan_rows if r["current_source_check"] != "PASS"
        ]

        plan_status_failures = [
            p for p in plans if p.get("status") != "COMPLETED"
        ]

        problems = []
        problems.extend(user_problems)
        problems.extend(no_year_problems)

        if integrity != "ok":
            problems.append(f"integrity_check={integrity}")
        if fk_rows:
            problems.append(f"foreign_key_check có {len(fk_rows)} lỗi.")
        if school_failures:
            problems.append(
                f"Có {len(school_failures)} trạng thái trường sai."
            )
        if direct_failures:
            problems.append(
                f"Có {len(direct_failures)} bảng còn dữ liệu năm hiện hành tại nguồn."
            )
        if plan_status_failures:
            problems.append(
                f"Có {len(plan_status_failures)} plan QĐ3805 chưa COMPLETED."
            )

        # Users source exact expectation.
        source_school_login_count = sum(
            1 for r in source_user_rows
            if r["kind"] == "SCHOOL_LOGIN"
        )
        source_other_user_count = sum(
            1 for r in source_user_rows
            if r["kind"] != "SCHOOL_LOGIN"
        )

        if source_school_login_count != len(source_ids):
            problems.append(
                f"Expected {len(source_ids)} tài khoản Trường nguồn còn khóa, "
                f"thực tế={source_school_login_count}."
            )
        if source_other_user_count != 0:
            problems.append(
                f"Còn {source_other_user_count} user không phải SCHOOL_LOGIN tại nguồn."
            )

        # Audit logs are allowed; report count.
        audit_log_source_count = sum(
            int(r["source_rows"])
            for r in no_year_rows
            if r["table"] in AUDIT_LOG_TABLES
        )

        gate_rows = [
            {
                "check": "qd3805_plan_count",
                "result": "PASS" if len(plans) == 6 else "FAIL",
                "detail": str(len(plans)),
            },
            {
                "check": "qd3805_plan_status_completed",
                "result": "PASS" if not plan_status_failures else "FAIL",
                "detail": f"not_completed={len(plan_status_failures)}",
            },
            {
                "check": "current_school_year",
                "result": "PASS",
                "detail": f"{current_year_id}:{years.get(current_year_id, '')}",
            },
            {
                "check": "source_school_count",
                "result": "PASS" if len(source_ids) == 7 else "REVIEW",
                "detail": str(len(source_ids)),
            },
            {
                "check": "target_school_count",
                "result": "PASS" if len(target_ids) == 6 else "REVIEW",
                "detail": str(len(target_ids)),
            },
            {
                "check": "school_active_status",
                "result": "PASS" if not school_failures else "FAIL",
                "detail": f"failures={len(school_failures)}",
            },
            {
                "check": "source_school_login_locked",
                "result": (
                    "PASS"
                    if source_school_login_count == len(source_ids)
                    and source_other_user_count == 0
                    and not user_problems
                    else "FAIL"
                ),
                "detail": (
                    f"school_logins={source_school_login_count}; "
                    f"other_users={source_other_user_count}; "
                    f"user_problems={len(user_problems)}"
                ),
            },
            {
                "check": "direct_year_source_residuals",
                "result": "PASS" if not direct_failures else "FAIL",
                "detail": f"tables_with_residuals={len(direct_failures)}",
            },
            {
                "check": "key_tables_by_plan",
                "result": "PASS" if not key_failures else "FAIL",
                "detail": f"plan_table_failures={len(key_failures)}",
            },
            {
                "check": "no_year_unknown_source_rows",
                "result": "PASS" if not no_year_problems else "REVIEW",
                "detail": " | ".join(no_year_problems),
            },
            {
                "check": "audit_logs_kept_at_source",
                "result": "PASS",
                "detail": str(audit_log_source_count),
            },
            {
                "check": "foreign_key_check",
                "result": "PASS" if not fk_rows else "FAIL",
                "detail": str(len(fk_rows)),
            },
            {
                "check": "integrity_check",
                "result": "PASS" if integrity == "ok" else "FAIL",
                "detail": str(integrity),
            },
        ]

        safe = not problems

        # Write reports.
        write_csv(
            out_dir / "400_QD3805_PLAN_MAP.csv",
            [
                "plan_id", "document_code",
                "school_year_id", "school_year_label",
                "commune_id", "commune_name", "level_code",
                "source_school_ids", "source_school_names",
                "target_school_id", "target_school_name",
                "status",
            ],
            plan_rows,
        )
        write_csv(
            out_dir / "401_SCHOOL_STATUS.csv",
            [
                "plan_id", "role", "school_id",
                "school_name", "school_code",
                "commune_id", "commune_name",
                "is_active", "expected_active", "status_check",
            ],
            school_status_rows,
        )
        write_csv(
            out_dir / "402_USERS_AT_SOURCE.csv",
            [
                "id", "username", "full_name", "role_id",
                "school_id", "school_name", "is_active",
                "kind", "expected", "check",
            ],
            source_user_rows,
        )
        write_csv(
            out_dir / "403_USERS_AT_TARGET_SUMMARY.csv",
            [
                "target_school_id", "target_school_name",
                "total_users",
                "school_login_total", "school_login_active",
                "cbql_total", "cbql_active",
                "teacher_total", "teacher_active",
                "other_total", "other_active",
            ],
            target_user_summary,
        )
        write_csv(
            out_dir / "404_DIRECT_YEAR_SOURCE_RESIDUALS.csv",
            [
                "table", "category",
                "source_current_year_rows",
                "expected", "check",
            ],
            direct_residuals,
        )
        write_csv(
            out_dir / "405_HISTORICAL_SOURCE_PRESERVED.csv",
            [
                "table", "category",
                "source_historical_rows", "policy",
            ],
            historical_rows,
        )
        write_csv(
            out_dir / "406_NO_YEAR_SOURCE_ROWS.csv",
            [
                "table", "category", "source_rows",
                "policy", "result", "detail",
            ],
            no_year_rows,
        )
        write_csv(
            out_dir / "407_KEY_TABLES_BY_PLAN.csv",
            [
                "plan_id", "table", "category",
                "source_ids", "target_id", "target_name",
                "source_current_year_rows",
                "source_historical_rows",
                "target_current_year_rows",
                "current_source_check",
            ],
            key_plan_rows,
        )
        write_csv(
            out_dir / "408_TARGET_CURRENT_ROWS_BY_TABLE.csv",
            [
                "table", "category",
                "target_current_year_rows",
            ],
            target_current_rows,
        )
        write_csv(
            out_dir / "409_TARGET_VISIBLE_DATA_GROUPS.csv",
            [
                "data_group",
                "current_rows_at_targets",
                "note",
            ],
            visible_rows,
        )
        write_csv(
            out_dir / "410_TABLE_POLICY_CATALOG.csv",
            [
                "table", "category",
                "has_school_id", "has_school_year_id",
                "policy",
            ],
            table_policy_rows,
        )
        write_csv(
            out_dir / "411_FOREIGN_KEY_CHECK.csv",
            ["table", "rowid", "parent", "fk_index"],
            fk_rows,
        )
        write_csv(
            out_dir / "412_GATE_V10.csv",
            ["check", "result", "detail"],
            gate_rows,
        )

        # Summary text.
        summary = out_dir / "00_TONG_QUAN_V10.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V10 - KIỂM TOÁN SAU SÁP NHẬP TOÀN HỆ THỐNG QĐ 3805\n"
            )
            f.write("=" * 120 + "\n")
            f.write("CHỈ ĐỌC - KHÔNG SỬA DATABASE / JSON / MÃ NGUỒN\n\n")

            f.write(f"Database: {DB_PATH}\n")
            f.write(f"Plan file: {PLAN_FILE}\n")
            f.write(
                f"Năm hiện hành: {current_year_id} - "
                f"{years.get(current_year_id, '')}\n"
            )
            f.write(f"Số nhóm QĐ 3805: {len(plans)}\n")
            f.write(f"Trường nguồn: {len(source_ids)} -> {source_ids}\n")
            f.write(f"Trường đích: {len(target_ids)} -> {target_ids}\n\n")

            f.write("TRẠNG THÁI TRƯỜNG\n")
            f.write(
                f"- Sai trạng thái active/locked: {len(school_failures)}\n"
            )

            f.write("\nTÀI KHOẢN\n")
            f.write(
                f"- Tài khoản Trường nguồn đã khóa: {source_school_login_count}\n"
            )
            f.write(
                f"- User khác còn tại nguồn: {source_other_user_count}\n"
            )
            f.write(
                f"- User problems: {len(user_problems)}\n"
            )

            f.write("\nDỮ LIỆU THEO NĂM\n")
            f.write(
                f"- Bảng có current-year residual tại nguồn: {len(direct_failures)}\n"
            )
            f.write(
                f"- Key-plan/table failures: {len(key_failures)}\n"
            )

            f.write("\nBẢNG KHÔNG CÓ school_year_id\n")
            for r in no_year_rows:
                f.write(
                    f"- {r['table']}: {r['source_rows']} | "
                    f"{r['policy']} | {r['result']}\n"
                )

            f.write("\nKIỂM TRA DATABASE\n")
            f.write(f"- integrity_check: {integrity}\n")
            f.write(f"- foreign_key_check: {len(fk_rows)} lỗi\n")

            f.write("\nCỔNG V10\n")
            for g in gate_rows:
                f.write(
                    f"- [{g['result']}] {g['check']}: {g['detail']}\n"
                )

            f.write("\nKẾT LUẬN\n")
            f.write(
                "SAFE_POST_MERGER_QD3805 = "
                + ("YES" if safe else "NO")
                + "\n"
            )
            if problems:
                f.write("\nVẤN ĐỀ CẦN XỬ LÝ\n")
                for p in problems:
                    f.write("- " + p + "\n")
            else:
                f.write(
                    "- Không phát hiện dữ liệu năm hiện hành còn sót tại trường nguồn.\n"
                )
                f.write(
                    "- Lịch sử vẫn được giữ tại nguồn theo chính sách.\n"
                )
                f.write(
                    "- Audit log giữ tại đơn vị phát sinh là đúng.\n"
                )

        zip_path = ROOT / (
            f"dry_run_kiem_toan_sau_sap_nhap_QD3805_v10_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 120)
        print("HOÀN THÀNH DRY-RUN V10")
        print("=" * 120)
        print(f"QĐ 3805 plans: {len(plans)}")
        print(f"Trường nguồn: {len(source_ids)}")
        print(f"Trường đích: {len(target_ids)}")
        print(f"School status failures: {len(school_failures)}")
        print(f"Source school logins locked: {source_school_login_count}")
        print(f"Other users còn tại nguồn: {source_other_user_count}")
        print(f"Direct-year residual tables: {len(direct_failures)}")
        print(f"No-year tables cần review: {len(no_year_problems)}")
        print(f"Audit log rows giữ tại nguồn: {audit_log_source_count}")
        print(f"FK errors: {len(fk_rows)}")
        print(f"integrity_check: {integrity}")
        print(
            "SAFE_POST_MERGER_QD3805: "
            + ("YES" if safe else "NO")
        )
        print(f"ZIP: {zip_path}")
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")

    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except AuditAbort as exc:
        print()
        print("=" * 120)
        print("ĐÃ DỪNG DRY-RUN V10")
        print("=" * 120)
        print(str(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as exc:
        print()
        print("=" * 120)
        print("LỖI SQLITE TRONG V10")
        print("=" * 120)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as exc:
        print()
        print("=" * 120)
        print("LỖI KHÔNG DỰ KIẾN TRONG V10")
        print("=" * 120)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(4)
