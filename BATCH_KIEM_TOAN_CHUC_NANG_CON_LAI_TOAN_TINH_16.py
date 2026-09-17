# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
EXPORT_DIR = ROOT / "exports"

OUT = EXPORT_DIR / "BATCH_KIEM_TOAN_CHUC_NANG_CON_LAI_TOAN_TINH_16.txt"
MATRIX_CSV = EXPORT_DIR / "BATCH_16_MA_TRAN_CHUC_NANG_CON_LAI.csv"
ROUTES_JSON = EXPORT_DIR / "BATCH_16_ROUTE_AUDIT.json"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8
MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

SKIP_DIRS = {
    ".venv", "venv", ".git", "__pycache__", "node_modules",
    "backups", "exports",
}

DOMAINS = {
    "CBQL_CHUC_VU": {
        "tables": ["staff_year_records", "staff_members"],
        "keywords": [
            "position_group", "position_title", "staff_year_records",
            "staff_form", "staff/list", "staff/form", "CBQL"
        ],
        "must_have": ["position_group", "position_title"],
        "purpose": "Trường tự sửa lại chức vụ HT/PHT sau khi đã chuẩn hóa chung thành CBQL",
    },
    "NETWORK_HIEN_HANH": {
        "tables": ["school_network_year_data"],
        "keywords": [
            "school_network_year_data", "network_year_data",
            "mang_luoi", "mạng lưới", "national_standard"
        ],
        "must_have": ["school_network_year_data"],
        "purpose": "Nhập/cập nhật số liệu hiện hành cho các merger target còn thiếu",
    },
    "DOI_CHIEU_HOC_SINH": {
        "tables": [
            "student_reconciliation_source_states",
            "student_reconciliation_state_enrollments",
            "student_reconciliation_import_logs",
        ],
        "keywords": [
            "student_reconciliation", "reconciliation",
            "doi_chieu", "đối chiếu"
        ],
        "must_have": ["student_reconciliation"],
        "purpose": "Đối chiếu dữ liệu điều tra với học sinh",
    },
    "KHUYET_TAT": {
        "tables": [
            "survey_person_year_records",
            "survey_person_year_disability_types",
        ],
        "keywords": [
            "disability", "khuyet_tat", "khuyết tật",
            "disability_status", "disability_type"
        ],
        "must_have": ["disability_status"],
        "purpose": "Theo dõi và báo cáo trẻ/người khuyết tật",
    },
    "CSVC_TBDH": {
        "tables": [
            "school_facility_year_items",
            "school_structured_report_inputs",
        ],
        "keywords": [
            "facility", "equipment", "csvc", "tbdh",
            "TH_01_CSVC", "THCS_01_CSVC", "MN_01_CSVC"
        ],
        "must_have": ["csvc"],
        "purpose": "Nhập và báo cáo cơ sở vật chất, thiết bị dạy học",
    },
    "TAI_CHINH": {
        "tables": [
            "finance_year_entries",
            "finance_report_values",
        ],
        "keywords": [
            "finance", "financial", "tai_chinh", "tài chính"
        ],
        "must_have": ["finance"],
        "purpose": "Nhập và báo cáo tài chính",
    },
    "TIEU_CHUAN": {
        "tables": [
            "school_network_year_data",
            "school_structured_report_inputs",
        ],
        "keywords": [
            "national_standard", "criterion", "criteria",
            "standard", "tieu_chuan", "tiêu chuẩn"
        ],
        "must_have": ["national_standard"],
        "purpose": "Tiêu chuẩn/công nhận phổ cập",
    },
    "DIEU_TRA_HO_DAN": {
        "tables": [
            "survey_batches", "households", "survey_people",
            "survey_forms", "survey_school_assignments",
        ],
        "keywords": [
            "household", "survey_people", "survey_forms",
            "survey_school_assignments", "dieu_tra", "điều tra"
        ],
        "must_have": ["survey_forms"],
        "purpose": "Điều tra hộ dân và luồng giao phiếu",
    },
    "KHOA_TIEN_DO": {
        "tables": [
            "survey_commune_execution_states",
            "survey_execution_workflow_logs",
        ],
        "keywords": [
            "khoa_truong", "khoa_toan_xa",
            "is_commune_locked", "is_province_locked",
            "KHOA_TRUONG", "KHOA_XA"
        ],
        "must_have": ["khoa_truong", "khoa_toan_xa"],
        "purpose": "Khóa trường/xã/Sở theo tiến độ",
    },
    "BACKUP_RESTORE": {
        "tables": [],
        "keywords": [
            "backup", "restore", "khoi_phuc", "khôi phục"
        ],
        "must_have": ["backup"],
        "purpose": "Backup và khôi phục database",
    },
}

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


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone() is not None


def cols(conn, table):
    if not table_exists(conn, table):
        return []
    return [
        r[1] for r in conn.execute(
            f"PRAGMA table_info({qi(table)})"
        ).fetchall()
    ]


def table_count(conn, table):
    if not table_exists(conn, table):
        return None
    return int(conn.execute(
        f"SELECT COUNT(*) FROM {qi(table)}"
    ).fetchone()[0])


def year_counts(conn, table):
    c = cols(conn, table)
    yc = None
    for cand in ("school_year_id", "target_school_year_id", "year_id"):
        if cand in c:
            yc = cand
            break
    if not yc:
        return None

    out = {}
    for y in (BASE_YEAR_ID, CURRENT_YEAR_ID, FUTURE_YEAR_ID):
        try:
            out[str(y)] = int(conn.execute(
                f"SELECT COUNT(*) FROM {qi(table)} WHERE {qi(yc)}=?",
                (y,)
            ).fetchone()[0])
        except sqlite3.Error:
            out[str(y)] = None
    return out


def source_files():
    result = []
    if not APP.exists():
        return result

    for p in APP.rglob("*"):
        if not p.is_file():
            continue
        if any(part.lower() in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in {".py", ".html", ".jinja2", ".js"}:
            continue
        try:
            if p.stat().st_size > 5 * 1024 * 1024:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        result.append((p, text))
    return result


def extract_routes(py_path: Path, text: str):
    routes = []
    if py_path.suffix.lower() != ".py":
        return routes

    try:
        tree = ast.parse(text)
    except Exception:
        return routes

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        decorators = []
        for d in node.decorator_list:
            if not isinstance(d, ast.Call):
                continue
            func = d.func
            method = None
            if isinstance(func, ast.Attribute):
                method = func.attr.lower()
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue

            path_value = None
            if d.args:
                a0 = d.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    path_value = a0.value

            decorators.append({
                "method": method.upper(),
                "path": path_value,
            })

        if decorators:
            try:
                body_text = ast.get_source_segment(text, node) or ""
            except Exception:
                body_text = ""
            for dec in decorators:
                routes.append({
                    "file": str(py_path.relative_to(ROOT)),
                    "function": node.name,
                    "method": dec["method"],
                    "path": dec["path"],
                    "body_excerpt": body_text[:3000],
                })

    return routes


def find_source_hits(files, keywords):
    hits = []
    lowered = [k.lower() for k in keywords]

    for p, text in files:
        low = text.lower()
        matched = [k for k in lowered if k in low]
        if not matched:
            continue

        hits.append({
            "file": str(p.relative_to(ROOT)),
            "matched": sorted(set(matched)),
        })

    return hits


def route_hits(routes, keywords):
    lowered = [k.lower() for k in keywords]
    out = []

    for r in routes:
        hay = " ".join([
            str(r.get("file") or ""),
            str(r.get("function") or ""),
            str(r.get("path") or ""),
            str(r.get("body_excerpt") or ""),
        ]).lower()

        matched = [k for k in lowered if k in hay]
        if matched:
            item = dict(r)
            item.pop("body_excerpt", None)
            item["matched"] = sorted(set(matched))
            out.append(item)

    return out


def template_form_hits(files, domain):
    """
    Kiểm tra riêng khả năng trường tự sửa chức vụ:
    tìm name/id có position_group, position_title trong template/source.
    """
    result = {
        "position_group_field": False,
        "position_title_field": False,
        "files": [],
    }
    if domain != "CBQL_CHUC_VU":
        return result

    for p, text in files:
        if p.suffix.lower() not in {".html", ".jinja2", ".py"}:
            continue
        low = text.lower()
        found = []
        if "position_group" in low:
            result["position_group_field"] = True
            found.append("position_group")
        if "position_title" in low:
            result["position_title_field"] = True
            found.append("position_title")
        if found:
            result["files"].append({
                "file": str(p.relative_to(ROOT)),
                "fields": found,
            })

    return result


def db_domain_profile(conn, domain, cfg):
    tables = []
    for t in cfg["tables"]:
        tables.append({
            "table": t,
            "exists": table_exists(conn, t),
            "columns": cols(conn, t),
            "total": table_count(conn, t),
            "year_counts": year_counts(conn, t),
        })

    profile = {"tables": tables}

    if domain == "CBQL_CHUC_VU":
        profile["generic_cbql_y2"] = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE school_year_id=?
              AND UPPER(TRIM(COALESCE(position_group,'')))='CBQL'
              AND UPPER(TRIM(COALESCE(position_title,'')))='CBQL'
            """,
            (CURRENT_YEAR_ID,)
        ).fetchone()[0])

    if domain == "NETWORK_HIEN_HANH":
        profile["missing_active_y2"] = []
        if table_exists(conn, "school_network_year_data"):
            for sid in [
                int(r[0]) for r in conn.execute(
                    "SELECT id FROM schools WHERE is_active=1 ORDER BY id"
                ).fetchall()
            ]:
                y1 = int(conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM school_network_year_data
                    WHERE school_id=? AND school_year_id=?
                    """,
                    (sid, BASE_YEAR_ID)
                ).fetchone()[0])
                y2 = int(conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM school_network_year_data
                    WHERE school_id=? AND school_year_id=?
                    """,
                    (sid, CURRENT_YEAR_ID)
                ).fetchone()[0])
                if y1 > 0 and y2 == 0:
                    profile["missing_active_y2"].append(sid)

    if domain == "DOI_CHIEU_HOC_SINH" and table_exists(conn, "student_reconciliation_source_states"):
        cur = conn.execute(
            """
            SELECT id,target_school_year_id,source_school_year_id,
                   commune_id,status,total_rows,valid_rows,
                   student_count,enrollment_count,class_count,import_count
            FROM student_reconciliation_source_states
            ORDER BY id
            """
        )
        names = [d[0] for d in cur.description]
        profile["source_states"] = [
            dict(zip(names, r)) for r in cur.fetchall()
        ]

    if domain == "KHUYET_TAT" and table_exists(conn, "survey_person_year_records"):
        c = cols(conn, "survey_person_year_records")
        if "disability_status" in c:
            profile["y2_disability"] = {
                "total": int(conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM survey_person_year_records
                    WHERE school_year_id=?
                    """,
                    (CURRENT_YEAR_ID,)
                ).fetchone()[0]),
                "status_filled": int(conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM survey_person_year_records
                    WHERE school_year_id=?
                      AND TRIM(COALESCE(disability_status,''))<>''
                    """,
                    (CURRENT_YEAR_ID,)
                ).fetchone()[0]),
                "type_filled": (
                    int(conn.execute(
                        """
                        SELECT COUNT(*)
                        FROM survey_person_year_records
                        WHERE school_year_id=?
                          AND TRIM(COALESCE(disability_type,''))<>''
                        """,
                        (CURRENT_YEAR_ID,)
                    ).fetchone()[0])
                    if "disability_type" in c else None
                ),
            }

    return profile


def classify(domain, db_profile, source_hits, routes, form_hits):
    route_count = len(routes)
    source_count = len(source_hits)

    existing_tables = [
        x for x in db_profile["tables"] if x["exists"]
    ]
    total_rows = sum(
        int(x["total"] or 0) for x in existing_tables
    )

    if domain == "CBQL_CHUC_VU":
        editable = (
            form_hits["position_group_field"]
            and form_hits["position_title_field"]
            and route_count > 0
        )
        if editable:
            return "READY_TRUONG_TU_SUA_CHUC_VU"
        return "CAN_KIEM_TRA_GIAO_DIEN_SUA_CHUC_VU"

    if domain == "NETWORK_HIEN_HANH":
        if route_count > 0 or source_count > 0:
            return "READY_CAP_NHAT_SO_LIEU_HIEN_HANH"
        return "THIEU_CHUC_NANG_CAP_NHAT_NETWORK"

    if domain == "DOI_CHIEU_HOC_SINH":
        states = db_profile.get("source_states") or []
        if states and any(str(x.get("status")) == "LOCKED" for x in states):
            return "READY_DA_CO_NGUON_DOI_CHIEU_LOCKED"
        if source_count > 0:
            return "READY_CHUC_NANG_CHO_DU_LIEU"
        return "CAN_BO_SUNG_CHUC_NANG"

    if domain == "KHUYET_TAT":
        if db_profile.get("y2_disability"):
            return "READY_CO_DU_LIEU_HIEN_HANH"
        if source_count > 0:
            return "READY_CHUC_NANG_CHO_DU_LIEU"
        return "CAN_BO_SUNG_CHUC_NANG"

    if domain in {"CSVC_TBDH", "TAI_CHINH"}:
        if source_count > 0 or route_count > 0:
            if total_rows == 0:
                return "READY_CHUC_NANG_NHUNG_CHUA_CO_DU_LIEU"
            return "READY_CO_DU_LIEU"
        return "CAN_BO_SUNG_CHUC_NANG"

    if domain == "TIEU_CHUAN":
        if source_count > 0:
            return "READY_THEO_DU_LIEU_HIEN_CO"
        return "CAN_BO_SUNG_CHUC_NANG"

    if domain == "DIEU_TRA_HO_DAN":
        if total_rows > 0 and source_count > 0:
            return "READY_DANG_CO_DU_LIEU_THUC_TE"
        return "CAN_KIEM_TRA"

    if domain == "KHOA_TIEN_DO":
        if source_count > 0 and route_count > 0:
            return "READY_DA_KIEM_CHUNG_TRUONG_XA"
        return "CAN_KIEM_TRA"

    if domain == "BACKUP_RESTORE":
        if source_count > 0:
            return "READY_CO_SOURCE"
        return "CAN_BO_SUNG_CHUC_NANG"

    return "CAN_KIEM_TRA"


def main():
    global LOG

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH 16 - KIỂM TOÁN CHỨC NĂNG CÒN LẠI TOÀN TỈNH")
    log("SAU KHI ĐÓNG ROLLOVER VÀ CHUẨN HÓA CBQL")
    log("CHỈ ĐỌC DATABASE + SOURCE CODE - KHÔNG GHI DB")
    log("=" * 160)

    sha = sha256_file(DB)
    log("DB_SHA =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)

    if sha != EXPECTED_DB_SHA:
        log("STOP = DB SHA khác nền Batch 14B/15.")
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

        files = source_files()
        all_routes = []
        for p, text in files:
            all_routes.extend(extract_routes(p, text))

        log("SOURCE_FILE_COUNT =", len(files))
        log("ROUTE_COUNT =", len(all_routes))

        rows = []
        audit_json = {}

        for domain, cfg in DOMAINS.items():
            s_hits = find_source_hits(files, cfg["keywords"])
            r_hits = route_hits(all_routes, cfg["keywords"])
            f_hits = template_form_hits(files, domain)
            db_profile = db_domain_profile(conn, domain, cfg)
            status = classify(
                domain, db_profile, s_hits, r_hits, f_hits
            )

            audit_json[domain] = {
                "purpose": cfg["purpose"],
                "status": status,
                "db_profile": db_profile,
                "source_hits": s_hits[:60],
                "route_hits": r_hits[:80],
                "form_hits": f_hits,
            }

            rows.append({
                "domain": domain,
                "purpose": cfg["purpose"],
                "status": status,
                "table_count": len(db_profile["tables"]),
                "existing_table_count": sum(
                    1 for x in db_profile["tables"] if x["exists"]
                ),
                "source_hit_file_count": len(s_hits),
                "route_hit_count": len(r_hits),
                "notes": (
                    "Trường tự cập nhật chức vụ thực tế"
                    if domain == "CBQL_CHUC_VU"
                    else ""
                ),
            })

            log("\n" + "-" * 140)
            log("DOMAIN =", domain)
            log("PURPOSE =", cfg["purpose"])
            log("STATUS =", status)
            log("DB_PROFILE =", json.dumps(
                db_profile, ensure_ascii=False, default=str
            ))
            log("SOURCE_HIT_COUNT =", len(s_hits))
            for x in s_hits[:30]:
                log(" SOURCE =", x)
            log("ROUTE_HIT_COUNT =", len(r_hits))
            for x in r_hits[:40]:
                log(" ROUTE =", x)
            if domain == "CBQL_CHUC_VU":
                log("FORM_HITS =", json.dumps(
                    f_hits, ensure_ascii=False, default=str
                ))

        with MATRIX_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            fields = [
                "domain", "purpose", "status",
                "table_count", "existing_table_count",
                "source_hit_file_count", "route_hit_count", "notes",
            ]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

        ROUTES_JSON.write_text(
            json.dumps(audit_json, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8-sig",
        )

        log("\n" + "=" * 160)
        log("KẾT LUẬN BATCH 16")
        log("=" * 160)
        log("MATRIX_CSV =", MATRIX_CSV)
        log("ROUTES_JSON =", ROUTES_JSON)
        log("DATABASE_WRITES_THIS_RUN = 0")
        log("DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
        log("BATCH_16_SUCCESS = YES")
        log(
            "NEXT_STAGE = Dựa vào ma trận chức năng để chọn Batch 17: "
            "nếu màn hình sửa CBQL đã đủ thì giữ nguyên; "
            "network chuyển sang nhập số liệu hiện hành; "
            "CSVC/TBDH, tài chính, tiêu chuẩn chỉ bổ sung nếu source hiện tại còn thiếu."
        )
        log("=" * 160)

    finally:
        conn.close()
        if LOG:
            LOG.close()

    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        try:
            log("\n" + "=" * 160)
            log("BATCH_16_SUCCESS = NO")
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
