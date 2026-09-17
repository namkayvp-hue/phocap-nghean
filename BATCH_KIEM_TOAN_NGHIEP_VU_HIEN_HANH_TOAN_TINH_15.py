# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
EXPORT_DIR = ROOT / "exports"

OUT = EXPORT_DIR / "BATCH_KIEM_TOAN_NGHIEP_VU_HIEN_HANH_TOAN_TINH_15.txt"
NETWORK_CSV = EXPORT_DIR / "BATCH_15_NETWORK_CAN_CAP_NHAT_THUC_TE.csv"
CBQL_CSV = EXPORT_DIR / "BATCH_15_CBQL_SAU_CHUAN_HOA.csv"
MANUAL_SPLIT_CSV = EXPORT_DIR / "BATCH_15_3_NGUON_TACH_DIEM_CHO_PHAN_BO.csv"
MODULE_JSON = EXPORT_DIR / "BATCH_15_TONG_HOP_PHAN_HE.json"

# Nền ngay sau Batch 14B.
EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

LOG = None


def log(*args):
    s = " ".join(str(x) for x in args)
    print(s)
    if LOG:
        LOG.write(s + "\n")
        LOG.flush()


def qi(name):
    return '"' + str(name).replace('"', '""') + '"'


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def table_exists(conn, table):
    return one(
        conn,
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ) is not None


def table_names(conn):
    return [
        r[0] for r in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]


def cols(conn, table):
    return [
        r[1] for r in conn.execute(
            f"PRAGMA table_info({qi(table)})"
        ).fetchall()
    ]


def school(conn, sid):
    return one(
        conn,
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    )


def active_school_ids(conn):
    return [
        int(r[0]) for r in conn.execute(
            "SELECT id FROM schools WHERE is_active=1 ORDER BY id"
        ).fetchall()
    ]


def count_sy(conn, table, sid, year_id):
    if not table_exists(conn, table):
        return 0
    c = cols(conn, table)
    if "school_id" not in c or "school_year_id" not in c:
        return 0
    return int(one(
        conn,
        f"""
        SELECT COUNT(*)
        FROM {qi(table)}
        WHERE school_id=? AND school_year_id=?
        """,
        (sid, year_id)
    )[0])


def official_target_ids(conn):
    if not table_exists(conn, "school_merger_official_executions"):
        return []
    return [
        int(r[0]) for r in conn.execute(
            """
            SELECT DISTINCT target_school_id
            FROM school_merger_official_executions
            WHERE school_year_id=?
              AND target_school_id IS NOT NULL
            ORDER BY target_school_id
            """,
            (CURRENT_YEAR_ID,)
        ).fetchall()
    ]


def official_exec_map(conn):
    out = defaultdict(list)
    if not table_exists(conn, "school_merger_official_executions"):
        return out

    rows = conn.execute(
        """
        SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json
        FROM school_merger_official_executions
        WHERE school_year_id=?
        ORDER BY id
        """,
        (CURRENT_YEAR_ID,)
    ).fetchall()

    for r in rows:
        try:
            source_ids = [int(x) for x in json.loads(r[4] or "[]")]
        except Exception:
            source_ids = []

        out[int(r[3])].append({
            "id": int(r[0]),
            "plan_id": r[1],
            "operation_id": r[2],
            "source_ids": source_ids,
        })
    return out


def audit_cbql(conn):
    targets = official_target_ids(conn)
    rows_out = []
    total_generic = 0
    residual_titles = []

    for sid in targets:
        s = school(conn, sid)

        total_staff = int(one(
            conn,
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE school_id=? AND school_year_id=?
            """,
            (sid, CURRENT_YEAR_ID)
        )[0])

        generic_cbql = int(one(
            conn,
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE school_id=? AND school_year_id=?
              AND UPPER(TRIM(COALESCE(position_group,'')))='CBQL'
              AND UPPER(TRIM(COALESCE(position_title,'')))='CBQL'
            """,
            (sid, CURRENT_YEAR_ID)
        )[0])

        residual = conn.execute(
            """
            SELECT id,staff_member_id,position_group,position_title
            FROM staff_year_records
            WHERE school_id=? AND school_year_id=?
              AND (
                    LOWER(COALESCE(position_title,'')) LIKE '%hiệu trưởng%'
                 OR LOWER(COALESCE(position_title,'')) LIKE '%hiệu truong%'
                 OR LOWER(COALESCE(position_title,'')) LIKE '%hieu trưởng%'
                 OR LOWER(COALESCE(position_title,'')) LIKE '%hieu truong%'
              )
            """,
            (sid, CURRENT_YEAR_ID)
        ).fetchall()

        total_generic += generic_cbql

        for r in residual:
            residual_titles.append({
                "school_id": sid,
                "staff_year_record_id": r[0],
                "staff_member_id": r[1],
                "position_group": r[2],
                "position_title": r[3],
            })

        rows_out.append({
            "school_id": sid,
            "school_code": s[2] if s else "",
            "school_name": s[3] if s else "",
            "commune_id": s[1] if s else "",
            "staff_y2_total": total_staff,
            "generic_cbql_count": generic_cbql,
            "residual_ht_pht_title_count": len(residual),
            "school_action": (
                "Tự cập nhật chức vụ thực tế cho các dòng CBQL"
                if generic_cbql > 0
                else "Không có dòng CBQL chung từ Batch 14B"
            ),
        })

    with CBQL_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        fields = [
            "school_id", "school_code", "school_name", "commune_id",
            "staff_y2_total", "generic_cbql_count",
            "residual_ht_pht_title_count", "school_action",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)

    return {
        "official_target_count": len(targets),
        "generic_cbql_total": total_generic,
        "residual_ht_pht_title_count": len(residual_titles),
        "residual_rows": residual_titles,
        "rows": rows_out,
    }


def read_network_rows(conn, sid, year_id):
    if not table_exists(conn, "school_network_year_data"):
        return []
    cur = conn.execute(
        """
        SELECT id,school_id,school_year_id,level_code,data_json,source_name
        FROM school_network_year_data
        WHERE school_id=? AND school_year_id=?
        ORDER BY id
        """,
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def value_kind(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "BOOL"
    if isinstance(v, (int, float)):
        return "NUMBER"
    if isinstance(v, str):
        return "TEXT"
    return type(v).__name__.upper()


def classify_conflict(key, vals):
    if all(v == vals[0] for v in vals):
        return None

    kinds = {value_kind(v) for v in vals}
    key_low = str(key).lower()

    if "national_standard" in key_low:
        return "STATUS_CONFLICT"

    if "NULL" in kinds and len(kinds) > 1:
        return "NULL_MIX"

    if kinds == {"NUMBER"}:
        return "NUMERIC_DIFFERENCE"

    return "OTHER_CONFLICT"


def audit_remaining_network(conn):
    exmap = official_exec_map(conn)
    rows_out = []
    class_counter = Counter()

    for tid in sorted(exmap):
        if count_sy(conn, "school_network_year_data", tid, BASE_YEAR_ID) <= 0:
            continue
        if count_sy(conn, "school_network_year_data", tid, CURRENT_YEAR_ID) > 0:
            continue

        execs = exmap[tid]
        source_ids = execs[0]["source_ids"] if len(execs) == 1 else []
        component_ids = [tid] + source_ids

        grouped = defaultdict(list)
        parse_errors = []

        for cid in component_ids:
            for row in read_network_rows(conn, cid, BASE_YEAR_ID):
                try:
                    payload = json.loads(row["data_json"])
                except Exception as exc:
                    parse_errors.append({
                        "component_school_id": cid,
                        "row_id": row["id"],
                        "error": repr(exc),
                    })
                    continue

                grouped[str(row.get("level_code") or "")].append({
                    "component_school_id": cid,
                    "row_id": row["id"],
                    "payload": payload,
                })

        conflicts = []

        for level_code, items in grouped.items():
            all_keys = set()
            for item in items:
                p = item["payload"]
                if isinstance(p, dict):
                    all_keys.update(p.keys())

            for key in sorted(all_keys):
                vals = []
                for item in items:
                    p = item["payload"]
                    vals.append(p.get(key) if isinstance(p, dict) else None)

                cls = classify_conflict(key, vals)
                if cls:
                    class_counter[cls] += 1
                    conflicts.append({
                        "level_code": level_code,
                        "key": key,
                        "class": cls,
                        "values": vals,
                    })

        reason_classes = sorted({x["class"] for x in conflicts})
        if parse_errors:
            reason_classes.append("JSON_PARSE_ERROR")
            class_counter["JSON_PARSE_ERROR"] += len(parse_errors)

        s = school(conn, tid)

        # Nhóm hành động:
        if "STATUS_CONFLICT" in reason_classes:
            action_group = "NHAP_XAC_NHAN_TRANG_THAI_HIEN_HANH"
        elif "NULL_MIX" in reason_classes:
            action_group = "BO_SUNG_SO_LIEU_CON_THIEU"
        elif reason_classes == ["NUMERIC_DIFFERENCE"]:
            action_group = "CAN_QUY_TAC_TONG_HOP_HOAC_NHAP_SO_LIEU_THUC_TE"
        else:
            action_group = "RA_SOAT_THU_CONG"

        rows_out.append({
            "target_id": tid,
            "school_code": s[2] if s else "",
            "school_name": s[3] if s else "",
            "source_ids": ",".join(str(x) for x in source_ids),
            "level_codes": ",".join(sorted(grouped.keys())),
            "reason_classes": "|".join(reason_classes),
            "conflict_count": len(conflicts),
            "action_group": action_group,
            "conflicts_json": json.dumps(conflicts, ensure_ascii=False),
            "parse_errors_json": json.dumps(parse_errors, ensure_ascii=False),
        })

    with NETWORK_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        fields = [
            "target_id", "school_code", "school_name", "source_ids",
            "level_codes", "reason_classes", "conflict_count",
            "action_group", "conflicts_json", "parse_errors_json",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)

    return rows_out, class_counter


def audit_manual_split(conn):
    rows_out = []

    for sid in sorted(MANUAL_SPLIT_SOURCE_IDS):
        s = school(conn, sid)
        y1 = count_sy(conn, "staff_year_records", sid, BASE_YEAR_ID)
        y2 = count_sy(conn, "staff_year_records", sid, CURRENT_YEAR_ID)

        rows_out.append({
            "source_school_id": sid,
            "school_code": s[2] if s else "",
            "school_name": s[3] if s else "",
            "commune_id": s[1] if s else "",
            "staff_y1": y1,
            "staff_y2": y2,
            "status": "CHO_DANH_SACH_PHAN_BO_THUC_TE",
        })

    with MANUAL_SPLIT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        fields = [
            "source_school_id", "school_code", "school_name",
            "commune_id", "staff_y1", "staff_y2", "status",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)

    return rows_out


def year_counts(conn, table):
    c = cols(conn, table)
    yc = None
    for cand in ("school_year_id", "year_id", "target_school_year_id"):
        if cand in c:
            yc = cand
            break

    if not yc:
        return None

    result = {}
    for year_id in (BASE_YEAR_ID, CURRENT_YEAR_ID, FUTURE_YEAR_ID):
        try:
            result[str(year_id)] = int(one(
                conn,
                f"SELECT COUNT(*) FROM {qi(table)} WHERE {qi(yc)}=?",
                (year_id,)
            )[0])
        except sqlite3.Error:
            result[str(year_id)] = None
    return result


def audit_module_tables(conn):
    groups = defaultdict(list)

    for table in table_names(conn):
        low = table.lower()

        if any(x in low for x in ("student", "enrollment", "class")):
            groups["hoc_sinh_lop"].append(table)

        if any(x in low for x in ("reconciliation", "comparison", "followup")):
            groups["doi_chieu_hoc_sinh"].append(table)

        if any(x in low for x in ("survey", "household", "investigation")):
            groups["dieu_tra_ho_dan"].append(table)

        if any(x in low for x in ("disab", "khuyet")):
            groups["khuyet_tat"].append(table)

        if any(x in low for x in ("facility", "equipment")):
            groups["csvc_tbdh"].append(table)

        if any(x in low for x in ("finance", "financial")):
            groups["tai_chinh"].append(table)

        if any(x in low for x in ("standard", "criterion", "criteria")):
            groups["tieu_chuan"].append(table)

        if any(x in low for x in ("historical", "baseline")):
            groups["du_lieu_lich_su"].append(table)

        if any(x in low for x in ("report", "summary", "indicator")):
            groups["bao_cao"].append(table)

    result = {}

    for domain, tables in sorted(groups.items()):
        items = []
        for table in sorted(set(tables)):
            total = int(one(
                conn, f"SELECT COUNT(*) FROM {qi(table)}"
            )[0])
            items.append({
                "table": table,
                "total": total,
                "year_counts": year_counts(conn, table),
            })
        result[domain] = items

    # Các trạng thái nghiệp vụ quan trọng.
    if table_exists(conn, "student_reconciliation_source_states"):
        cur = conn.execute(
            "SELECT * FROM student_reconciliation_source_states ORDER BY id"
        )
        names = [d[0] for d in cur.description]
        result["doi_chieu_source_states"] = [
            dict(zip(names, r)) for r in cur.fetchall()
        ]

    if table_exists(conn, "survey_person_year_records"):
        c = cols(conn, "survey_person_year_records")
        if "disability_status" in c:
            result["khuyet_tat_hien_hanh"] = {
                "year2_total": int(one(
                    conn,
                    """
                    SELECT COUNT(*)
                    FROM survey_person_year_records
                    WHERE school_year_id=?
                    """,
                    (CURRENT_YEAR_ID,)
                )[0]),
                "status_filled": int(one(
                    conn,
                    """
                    SELECT COUNT(*)
                    FROM survey_person_year_records
                    WHERE school_year_id=?
                      AND TRIM(COALESCE(disability_status,''))<>''
                    """,
                    (CURRENT_YEAR_ID,)
                )[0]),
                "type_filled": (
                    int(one(
                        conn,
                        """
                        SELECT COUNT(*)
                        FROM survey_person_year_records
                        WHERE school_year_id=?
                          AND TRIM(COALESCE(disability_type,''))<>''
                        """,
                        (CURRENT_YEAR_ID,)
                    )[0])
                    if "disability_type" in c else None
                ),
            }

    return result


def audit_rollover_closure(conn):
    tables = (
        "staff_year_records",
        "classes",
        "student_enrollments",
        "school_staff_year_summaries",
        "school_mn01_gv_inputs",
        "school_network_year_data",
        "school_structured_report_inputs",
    )

    result = {}

    for table in tables:
        if not table_exists(conn, table):
            continue

        c = cols(conn, table)
        if "school_id" not in c or "school_year_id" not in c:
            continue

        missing = []
        for sid in active_school_ids(conn):
            y1 = count_sy(conn, table, sid, BASE_YEAR_ID)
            y2 = count_sy(conn, table, sid, CURRENT_YEAR_ID)
            if y1 > 0 and y2 == 0:
                missing.append(sid)

        result[table] = {
            "missing_y2_count": len(missing),
            "missing_y2_ids": missing,
        }

    return result


def main():
    global LOG

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH 15 - KIỂM TOÁN NGHIỆP VỤ HIỆN HÀNH TOÀN TỈNH SAU CHUẨN HÓA CBQL")
    log("CHỈ ĐỌC DB - KHÔNG GHI DỮ LIỆU")
    log("=" * 160)

    sha = sha256_file(DB)
    log("DB_SHA =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)

    if sha != EXPECTED_DB_SHA:
        log("STOP = DB SHA khác nền Batch 14B.")
        return 1

    conn = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=60,
    )
    conn.execute("PRAGMA query_only=ON")

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()

        log("INTEGRITY =", integrity)
        log("FK =", len(fk))

        if integrity != "ok" or fk:
            log("STOP = Database health không đạt.")
            return 1

        log("\n" + "=" * 160)
        log("1. XÁC NHẬN CBQL SAU BATCH 14B")
        log("=" * 160)
        cbql = audit_cbql(conn)
        log("OFFICIAL_TARGET_COUNT =", cbql["official_target_count"])
        log("GENERIC_CBQL_TOTAL =", cbql["generic_cbql_total"])
        log("RESIDUAL_HT_PHT_TITLE_COUNT =", cbql["residual_ht_pht_title_count"])
        log("CBQL_CSV =", CBQL_CSV)

        if cbql["residual_ht_pht_title_count"] != 0:
            log("WARNING = Vẫn còn title HT/PHT tại official target.")

        log("\n" + "=" * 160)
        log("2. 33 NETWORK CÒN THIẾU - PHÂN LOẠI ĐỂ NHẬP/CẬP NHẬT THỰC TẾ")
        log("=" * 160)
        network_rows, network_classes = audit_remaining_network(conn)
        log("NETWORK_REMAINING_COUNT =", len(network_rows))
        log("NETWORK_CONFLICT_CLASSES =", dict(network_classes))
        for row in network_rows:
            log(" NETWORK =", json.dumps(
                row, ensure_ascii=False, default=str
            ))
        log("NETWORK_CSV =", NETWORK_CSV)

        log("\n" + "=" * 160)
        log("3. BA NGUỒN TÁCH ĐIỂM CÒN MANUAL")
        log("=" * 160)
        manual_split = audit_manual_split(conn)
        log("MANUAL_SPLIT =", json.dumps(
            manual_split, ensure_ascii=False, default=str
        ))
        log("MANUAL_SPLIT_CSV =", MANUAL_SPLIT_CSV)

        log("\n" + "=" * 160)
        log("4. ĐÓNG ROLLOVER CÁC BẢNG LÕI")
        log("=" * 160)
        closure = audit_rollover_closure(conn)
        log("ROLLOVER_CLOSURE =", json.dumps(
            closure, ensure_ascii=False, default=str
        ))

        log("\n" + "=" * 160)
        log("5. TRẠNG THÁI CÁC PHÂN HỆ")
        log("=" * 160)
        modules = audit_module_tables(conn)
        log("MODULE_STATUS =", json.dumps(
            modules, ensure_ascii=False, default=str
        ))

    finally:
        conn.close()

    summary = {
        "db_sha": sha,
        "cbql": {
            "official_target_count": cbql["official_target_count"],
            "generic_cbql_total": cbql["generic_cbql_total"],
            "residual_ht_pht_title_count": cbql["residual_ht_pht_title_count"],
        },
        "network": {
            "remaining_count": len(network_rows),
            "conflict_classes": dict(network_classes),
        },
        "manual_split": manual_split,
        "rollover_closure": closure,
        "module_status": modules,
        "policies": {
            "cbql": "HT_PHT_DA_DUA_CHUNG_CBQL_TRUONG_TU_SUA_CHUC_VU",
            "network": "NHAP_CAP_NHAT_SO_LIEU_HIEN_HANH_KHONG_COI_NULL_LA_0",
            "manual_split": "CHO_DANH_SACH_PHAN_BO_THUC_TE",
            "finance_facility_history": "KHONG_TU_TAO_NEU_KHONG_CO_BASELINE",
        },
    }

    MODULE_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8-sig",
    )

    log("\n" + "=" * 160)
    log("KẾT LUẬN BATCH 15")
    log("=" * 160)
    log("MODULE_JSON =", MODULE_JSON)
    log("DATABASE_WRITES_THIS_RUN = 0")
    log("DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
    log("BATCH_15_SUCCESS = YES")
    log(
        "NEXT_STAGE = Batch 16 chỉ xử lý các nghiệp vụ có quy tắc chắc chắn từ kết quả này; "
        "CBQL để trường tự cập nhật chức vụ, 3 nguồn tách điểm chờ danh sách phân bổ, "
        "network còn thiếu chuyển sang nhập/cập nhật số liệu hiện hành."
    )
    log("=" * 160)

    if LOG:
        LOG.close()

    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        try:
            log("\n" + "=" * 160)
            log("BATCH_15_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("DỪNG AN TOÀN.")
            log("=" * 160)
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        code = 1

    sys.exit(code)
