# -*- coding: utf-8 -*-
r"""
V13.12 - KHẢO SÁT VẬN HÀNH SAU SÁP NHẬP TOÀN TỈNH
====================================================

MỤC TIÊU
--------
Kiểm tra vận hành sau khi V13.11 đã khóa toàn bộ sáp nhập trường.

ĐẶC BIỆT KIỂM TRA 2 TRƯỜNG LIÊN CẤP:
1) Mường Quàng
   target 1593 - Trường THCS Châu Thôn
   phải được nhận diện ở cả TH và THCS.

2) Hữu Khuông
   target 1559 - PTDTBT THCS Hữu Khuông
   phải được nhận diện ở cả TH và THCS.

PHẠM VI KHẢO SÁT
----------------
A. DATABASE - CHỈ ĐỌC
- Danh mục trường active/inactive.
- Nhận diện cấp học theo school_network_year_data.
- Tài khoản trường/CBQL/GV/NV.
- Staff year records.
- Lớp.
- Student enrollments.
- Dữ liệu đầu vào báo cáo.
- Residual ở source cũ.
- Hai target liên cấp có CURRENT level TH + THCS.

B. MÃ NGUỒN - CHỈ ĐỌC
Quét các file liên quan đến:
- danh mục trường;
- tài khoản;
- đội ngũ;
- lớp;
- học sinh;
- báo cáo;
- menu/template.

Mục tiêu là phát hiện:
- nơi lọc trường chỉ bằng tên;
- nơi chỉ lấy một level_code;
- nơi không dùng school_network_year_data;
- nơi quên is_active;
- nơi có nguy cơ không hiển thị trường liên cấp ở cả TH và THCS.

C. ROUTE/TEMPLATE
- Liệt kê route liên quan.
- Liệt kê vị trí source dùng level_code / school_network_year_data /
  is_active / school_id.
- Không sửa bất kỳ file nào.

KẾT QUẢ
-------
Tạo ZIP:
C:\PhoCap\bao_cao_v13_12_van_hanh_sau_sap_nhap_YYYYMMDD_HHMMSS.zip

CHẠY
----
cd C:\PhoCap
.\.venv\Scripts\python.exe .\khao_sat_van_hanh_sau_sap_nhap_toan_tinh_v13_12.py
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"

YEAR_ID = 2
YEAR_CODE = "2026-2027"

LINKED = [
    {
        "label": "MUONG_QUANG",
        "source_id": 1150,
        "target_id": 1593,
        "expected_name": "Trường THCS Châu Thôn",
        "expected_levels": {"TH", "THCS"},
    },
    {
        "label": "HUU_KHUONG",
        "source_id": 1101,
        "target_id": 1559,
        "expected_name": "PTDTBT THCS Hữu Khuông",
        "expected_levels": {"TH", "THCS"},
    },
]

OTHER_TARGETS = [
    {
        "label": "QUANG_DONG_MN",
        "target_id": 614,
        "expected_levels": {"MN"},
    },
    {
        "label": "QUANG_DONG_TH",
        "target_id": 1232,
        "expected_levels": {"TH"},
    },
]

SOURCE_KEYWORDS = [
    "school_network_year_data",
    "_school_levels",
    "_structured_network_school_ids",
    "level_code",
    "is_active",
    "school_id",
    "School.name",
    "school.name",
    "ilike(",
    "startswith(",
    "truong_",
]

IMPORTANT_NAME_HINTS = [
    "school",
    "schools",
    "account",
    "user",
    "staff",
    "class",
    "student",
    "report",
    "menu",
    "index",
    "auth",
]


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=headers,
            extrasaction="ignore",
        )
        w.writeheader()
        w.writerows(rows)


def connect_ro() -> sqlite3.Connection:
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [
        str(r["name"])
        for r in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    ]


def db_health(con: sqlite3.Connection) -> tuple[str, int]:
    integrity = str(
        con.execute("PRAGMA integrity_check").fetchone()[0]
    )
    fk = len(
        con.execute("PRAGMA foreign_key_check").fetchall()
    )
    return integrity, fk


def school_levels(
    con: sqlite3.Connection,
    school_id: int,
    year_id: int,
) -> set[str]:
    if not table_exists(con, "school_network_year_data"):
        return set()

    rows = con.execute(
        """
        SELECT DISTINCT level_code
        FROM school_network_year_data
        WHERE school_id=? AND school_year_id=?
          AND level_code IS NOT NULL
        """,
        (school_id, year_id),
    ).fetchall()

    levels = {
        str(r[0]).strip().upper()
        for r in rows
        if str(r[0] or "").strip()
    }
    if levels:
        return levels

    # Fallback theo chronology/code thay vì school_year_id số.
    target = con.execute(
        "SELECT code FROM school_years WHERE id=?",
        (year_id,),
    ).fetchone()
    if target is None:
        return set()

    target_code = str(target[0] or "")
    previous = con.execute(
        """
        SELECT id,code
        FROM school_years
        WHERE code < ?
        ORDER BY code DESC,id DESC
        """,
        (target_code,),
    ).fetchall()

    for yr in previous:
        rows = con.execute(
            """
            SELECT DISTINCT level_code
            FROM school_network_year_data
            WHERE school_id=? AND school_year_id=?
              AND level_code IS NOT NULL
            """,
            (school_id, int(yr["id"])),
        ).fetchall()
        levels = {
            str(r[0]).strip().upper()
            for r in rows
            if str(r[0] or "").strip()
        }
        if levels:
            return levels

    return set()


def school_row(con: sqlite3.Connection, school_id: int) -> dict:
    row = con.execute(
        """
        SELECT s.id,s.code,s.name,s.commune_id,s.is_active,
               c.code AS commune_code,c.name AS commune_name
        FROM schools s
        LEFT JOIN communes c ON c.id=s.commune_id
        WHERE s.id=?
        """,
        (school_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Không tìm thấy school_id={school_id}.")
    return dict(row)


def count_for_school_year(
    con: sqlite3.Connection,
    table: str,
    school_id: int,
    year_id: int,
) -> int:
    if not table_exists(con, table):
        return -1
    cols = set(table_columns(con, table))
    if not {"school_id", "school_year_id"} <= cols:
        return -1
    return int(
        con.execute(
            f"""
            SELECT COUNT(*)
            FROM {qident(table)}
            WHERE school_id=? AND school_year_id=?
            """,
            (school_id, year_id),
        ).fetchone()[0]
        or 0
    )


def count_for_school(
    con: sqlite3.Connection,
    table: str,
    school_id: int,
) -> int:
    if not table_exists(con, table):
        return -1
    cols = set(table_columns(con, table))
    if "school_id" not in cols:
        return -1
    return int(
        con.execute(
            f"""
            SELECT COUNT(*)
            FROM {qident(table)}
            WHERE school_id=?
            """,
            (school_id,),
        ).fetchone()[0]
        or 0
    )


def current_data_for_school(
    con: sqlite3.Connection,
    school_id: int,
) -> dict[str, int]:
    result = {}

    for table in [
        "staff_year_records",
        "classes",
        "student_enrollments",
        "school_network_year_data",
        "school_mn01_gv_inputs",
        "school_mn01_csvc_inputs",
        "school_staff_year_summaries",
        "school_structured_report_inputs",
        "school_site_year_records",
        "school_facility_year_items",
        "school_class_year_attributes",
        "survey_person_year_records",
        "finance_year_entries",
    ]:
        if not table_exists(con, table):
            continue

        cols = set(table_columns(con, table))
        if {"school_id", "school_year_id"} <= cols:
            result[table] = count_for_school_year(
                con,
                table,
                school_id,
                YEAR_ID,
            )
        elif "school_id" in cols:
            result[table] = count_for_school(
                con,
                table,
                school_id,
            )

    return result


def linked_db_audit(
    con: sqlite3.Connection,
) -> tuple[list[dict], list[dict], list[dict]]:
    school_rows = []
    network_rows = []
    data_rows = []

    for item in [*LINKED, *OTHER_TARGETS]:
        sid = int(item["target_id"])
        school = school_row(con, sid)
        levels = school_levels(con, sid, YEAR_ID)

        expected_levels = set(item["expected_levels"])
        name_ok = True
        if "expected_name" in item:
            name_ok = str(school["name"] or "") == item["expected_name"]

        level_ok = levels == expected_levels
        active_ok = int(school["is_active"] or 0) == 1

        school_rows.append({
            "label": item["label"],
            "school_id": sid,
            "code": school["code"],
            "name": school["name"],
            "commune_id": school["commune_id"],
            "commune_code": school["commune_code"],
            "commune_name": school["commune_name"],
            "is_active": int(school["is_active"] or 0),
            "levels": ",".join(sorted(levels)),
            "expected_levels": ",".join(sorted(expected_levels)),
            "name_ok": name_ok,
            "level_ok": level_ok,
            "active_ok": active_ok,
            "result": (
                "PASS"
                if name_ok and level_ok and active_ok
                else "FAIL"
            ),
        })

        if table_exists(con, "school_network_year_data"):
            rows = con.execute(
                """
                SELECT id,school_id,school_year_id,level_code,
                       data_json,source_name,imported_at
                FROM school_network_year_data
                WHERE school_id=? AND school_year_id=?
                ORDER BY level_code,id
                """,
                (sid, YEAR_ID),
            ).fetchall()

            for row in rows:
                network_rows.append({
                    "label": item["label"],
                    **dict(row),
                })

        data = current_data_for_school(con, sid)
        for table, count in sorted(data.items()):
            data_rows.append({
                "label": item["label"],
                "school_id": sid,
                "table": table,
                "current_rows": count,
            })

    return school_rows, network_rows, data_rows


def source_residual_audit(
    con: sqlite3.Connection,
) -> list[dict]:
    rows = []

    for item in LINKED:
        source_id = int(item["source_id"])
        target_id = int(item["target_id"])

        source = school_row(con, source_id)
        target = school_row(con, target_id)

        regular_users = 0
        source_login_count = 0
        active_source_login = 0

        if table_exists(con, "users"):
            regular_users = int(
                con.execute(
                    """
                    SELECT COUNT(*)
                    FROM users
                    WHERE school_id=? AND username NOT LIKE 'truong_%'
                    """,
                    (source_id,),
                ).fetchone()[0]
                or 0
            )
            source_login_count = int(
                con.execute(
                    """
                    SELECT COUNT(*)
                    FROM users
                    WHERE school_id=? AND username LIKE 'truong_%'
                    """,
                    (source_id,),
                ).fetchone()[0]
                or 0
            )
            active_source_login = int(
                con.execute(
                    """
                    SELECT COUNT(*)
                    FROM users
                    WHERE school_id=? AND username LIKE 'truong_%'
                      AND is_active=1
                    """,
                    (source_id,),
                ).fetchone()[0]
                or 0
            )

        current_residual = 0
        detail = {}

        for table in year_aware_tables(con):
            n = int(
                con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {qident(table)}
                    WHERE school_id=? AND school_year_id IN (2,8)
                    """,
                    (source_id,),
                ).fetchone()[0]
                or 0
            )
            if n:
                detail[table] = n
                current_residual += n

        rows.append({
            "label": item["label"],
            "source_id": source_id,
            "source_name": source["name"],
            "source_is_active": int(source["is_active"] or 0),
            "target_id": target_id,
            "target_name": target["name"],
            "target_is_active": int(target["is_active"] or 0),
            "regular_users_at_source": regular_users,
            "source_school_login_count": source_login_count,
            "active_source_school_login": active_source_login,
            "current_future_residual": current_residual,
            "residual_detail_json": json.dumps(
                detail,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "result": (
                "PASS"
                if (
                    int(source["is_active"] or 0) == 0
                    and int(target["is_active"] or 0) == 1
                    and regular_users == 0
                    and source_login_count == 1
                    and active_source_login == 0
                    and current_residual == 0
                )
                else "FAIL"
            ),
        })

    return rows


def active_school_level_distribution(
    con: sqlite3.Connection,
) -> tuple[list[dict], list[dict]]:
    schools = con.execute(
        """
        SELECT id,code,name,commune_id,is_active
        FROM schools
        WHERE is_active=1
        ORDER BY commune_id,name COLLATE NOCASE,id
        """
    ).fetchall()

    distribution = defaultdict(int)
    multi_rows = []

    for row in schools:
        sid = int(row["id"])
        levels = school_levels(con, sid, YEAR_ID)

        key = "+".join(sorted(levels)) if levels else "UNKNOWN"
        distribution[key] += 1

        if len(levels) > 1:
            multi_rows.append({
                "school_id": sid,
                "code": row["code"],
                "name": row["name"],
                "commune_id": row["commune_id"],
                "levels": ",".join(sorted(levels)),
            })

    dist_rows = [
        {
            "level_scope": key,
            "active_school_count": count,
        }
        for key, count in sorted(distribution.items())
    ]

    return dist_rows, multi_rows


def year_aware_tables(
    con: sqlite3.Connection,
) -> list[str]:
    result = []

    for row in con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall():
        table = str(row["name"])
        cols = set(table_columns(con, table))
        if {"school_id", "school_year_id"} <= cols:
            result.append(table)

    return result


def scan_source_files() -> tuple[list[dict], list[dict], list[dict]]:
    if not APP.exists():
        return [], [], []

    file_rows = []
    line_rows = []
    route_rows = []

    candidates = []

    for pattern in ("*.py", "*.html", "*.js"):
        for path in APP.rglob(pattern):
            rel = path.relative_to(ROOT).as_posix()
            low = rel.lower()

            # Ưu tiên file có liên quan nghiệp vụ.
            score = sum(
                1
                for hint in IMPORTANT_NAME_HINTS
                if hint in low
            )

            try:
                text = path.read_text(
                    encoding="utf-8-sig"
                )
            except Exception:
                continue

            keyword_counts = {
                kw: text.count(kw)
                for kw in SOURCE_KEYWORDS
            }
            total_hits = sum(keyword_counts.values())

            if score > 0 or total_hits > 0:
                candidates.append((path, rel, text, score, keyword_counts))

    route_pattern = re.compile(
        r"@(?:router|app)\.(get|post|put|patch|delete)\(\s*[rRuUfF]*[\"']([^\"']+)[\"']"
    )

    for path, rel, text, score, keyword_counts in candidates:
        file_rows.append({
            "file": rel,
            "business_name_score": score,
            "total_keyword_hits": sum(keyword_counts.values()),
            **{
                f"count_{i+1}": keyword_counts[kw]
                for i, kw in enumerate(SOURCE_KEYWORDS)
            },
        })

        lines = text.splitlines()

        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()
            matched = [
                kw
                for kw in SOURCE_KEYWORDS
                if kw in line
            ]
            if not matched:
                continue

            # Cảnh báo tĩnh đơn giản.
            flags = []

            low = line.lower()

            if (
                ("school.name" in low or "school.name" in line)
                and (
                    "like" in low
                    or "startswith" in low
                    or "contains" in low
                )
            ):
                flags.append("NAME_BASED_LEVEL_OR_SCOPE")

            if "level_code" in line and "school_network_year_data" not in line:
                flags.append("LEVEL_CODE_REFERENCE")

            if "is_active" in line:
                flags.append("ACTIVE_FILTER_REFERENCE")

            if "school_network_year_data" in line:
                flags.append("NETWORK_LEVEL_REFERENCE")

            line_rows.append({
                "file": rel,
                "line": lineno,
                "matched_keywords": ",".join(matched),
                "risk_flags": ",".join(flags),
                "text": stripped[:500],
            })

        for m in route_pattern.finditer(text):
            line_no = text[:m.start()].count("\n") + 1
            route_rows.append({
                "file": rel,
                "line": line_no,
                "method": m.group(1).upper(),
                "path": m.group(2),
            })

    return file_rows, line_rows, route_rows


def summarize_source_risks(
    line_rows: list[dict],
) -> list[dict]:
    by_file = defaultdict(lambda: {
        "name_based": 0,
        "network_ref": 0,
        "level_ref": 0,
        "active_ref": 0,
        "lines": 0,
    })

    for row in line_rows:
        item = by_file[row["file"]]
        item["lines"] += 1
        flags = set(
            x for x in row["risk_flags"].split(",") if x
        )
        if "NAME_BASED_LEVEL_OR_SCOPE" in flags:
            item["name_based"] += 1
        if "NETWORK_LEVEL_REFERENCE" in flags:
            item["network_ref"] += 1
        if "LEVEL_CODE_REFERENCE" in flags:
            item["level_ref"] += 1
        if "ACTIVE_FILTER_REFERENCE" in flags:
            item["active_ref"] += 1

    rows = []

    for file, stats in sorted(by_file.items()):
        low = file.lower()

        relevant = any(
            hint in low
            for hint in [
                "school",
                "user",
                "account",
                "staff",
                "class",
                "student",
                "report",
                "menu",
            ]
        )

        if not relevant:
            continue

        if stats["network_ref"] > 0:
            level_support = "NETWORK_AWARE"
        elif stats["level_ref"] > 0:
            level_support = "LEVEL_CODE_ONLY_OR_UNKNOWN"
        else:
            level_support = "NO_LEVEL_SIGNAL_FOUND"

        risk = "LOW"
        reasons = []

        if stats["name_based"] > 0:
            risk = "HIGH"
            reasons.append("Có lọc/suy luận theo tên trường.")

        if (
            stats["network_ref"] == 0
            and stats["level_ref"] > 0
        ):
            if risk != "HIGH":
                risk = "MEDIUM"
            reasons.append(
                "Có dùng level_code nhưng chưa thấy tham chiếu "
                "school_network_year_data trong cùng file."
            )

        if (
            "school" in low
            and stats["active_ref"] == 0
        ):
            if risk == "LOW":
                risk = "MEDIUM"
            reasons.append(
                "File liên quan trường nhưng chưa thấy is_active."
            )

        rows.append({
            "file": file,
            "level_support": level_support,
            "name_based_hits": stats["name_based"],
            "network_hits": stats["network_ref"],
            "level_hits": stats["level_ref"],
            "active_hits": stats["active_ref"],
            "risk": risk,
            "reason": " | ".join(reasons),
        })

    return rows


def main() -> int:
    print("=" * 126)
    print("V13.12 - KHẢO SÁT VẬN HÀNH SAU SÁP NHẬP TOÀN TỈNH")
    print("=" * 126)
    print("CHỈ ĐỌC - KHÔNG SỬA DATABASE / PLAN JSON / SOURCE")

    for path in (DB_PATH, PLAN_FILE):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    with connect_ro() as con:
        integrity, fk = db_health(con)

        year = con.execute(
            "SELECT code,name FROM school_years WHERE id=?",
            (YEAR_ID,),
        ).fetchone()

        if year is None or str(year["code"] or "") != YEAR_CODE:
            raise RuntimeError(
                f"school_year_id={YEAR_ID} không còn là {YEAR_CODE}."
            )

        linked_school_rows, network_rows, linked_data_rows = (
            linked_db_audit(con)
        )
        source_rows = source_residual_audit(con)
        dist_rows, multi_rows = active_school_level_distribution(con)

        role_counts = []
        if table_exists(con, "users"):
            role_counts = [
                dict(r)
                for r in con.execute(
                    """
                    SELECT
                        CASE
                            WHEN u.school_id IS NULL THEN 'NO_SCHOOL'
                            ELSE 'HAS_SCHOOL'
                        END AS school_scope,
                        u.is_active,
                        COUNT(*) AS total
                    FROM users u
                    GROUP BY school_scope,u.is_active
                    ORDER BY school_scope,u.is_active
                    """
                ).fetchall()
            ]

    file_rows, line_rows, route_rows = scan_source_files()
    risk_rows = summarize_source_risks(line_rows)

    linked_fail = sum(
        row["result"] != "PASS"
        for row in linked_school_rows
    )
    source_fail = sum(
        row["result"] != "PASS"
        for row in source_rows
    )

    high_risk_files = [
        row
        for row in risk_rows
        if row["risk"] == "HIGH"
    ]
    medium_risk_files = [
        row
        for row in risk_rows
        if row["risk"] == "MEDIUM"
    ]

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    report_dir = (
        ROOT
        / f"bao_cao_v13_12_van_hanh_sau_sap_nhap_{stamp}"
    )
    zip_path = (
        ROOT
        / f"bao_cao_v13_12_van_hanh_sau_sap_nhap_{stamp}.zip"
    )
    report_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    write_csv(
        report_dir / "810_TRUONG_DICH_VA_LIEN_CAP.csv",
        [
            "label",
            "school_id",
            "code",
            "name",
            "commune_id",
            "commune_code",
            "commune_name",
            "is_active",
            "levels",
            "expected_levels",
            "name_ok",
            "level_ok",
            "active_ok",
            "result",
        ],
        linked_school_rows,
    )

    write_csv(
        report_dir / "811_NETWORK_CURRENT_LIEN_CAP.csv",
        [
            "label",
            "id",
            "school_id",
            "school_year_id",
            "level_code",
            "data_json",
            "source_name",
            "imported_at",
        ],
        network_rows,
    )

    write_csv(
        report_dir / "812_DU_LIEU_CURRENT_TRUONG_DICH.csv",
        [
            "label",
            "school_id",
            "table",
            "current_rows",
        ],
        linked_data_rows,
    )

    write_csv(
        report_dir / "813_SOURCE_CU_SAU_SAP_NHAP.csv",
        [
            "label",
            "source_id",
            "source_name",
            "source_is_active",
            "target_id",
            "target_name",
            "target_is_active",
            "regular_users_at_source",
            "source_school_login_count",
            "active_source_school_login",
            "current_future_residual",
            "residual_detail_json",
            "result",
        ],
        source_rows,
    )

    write_csv(
        report_dir / "814_PHAN_BO_TRUONG_ACTIVE_THEO_CAP.csv",
        [
            "level_scope",
            "active_school_count",
        ],
        dist_rows,
    )

    write_csv(
        report_dir / "815_TRUONG_DA_CAP.csv",
        [
            "school_id",
            "code",
            "name",
            "commune_id",
            "levels",
        ],
        multi_rows,
    )

    write_csv(
        report_dir / "816_SOURCE_FILES.csv",
        [
            "file",
            "business_name_score",
            "total_keyword_hits",
            *[
                f"count_{i+1}"
                for i in range(len(SOURCE_KEYWORDS))
            ],
        ],
        file_rows,
    )

    write_csv(
        report_dir / "817_SOURCE_LINES.csv",
        [
            "file",
            "line",
            "matched_keywords",
            "risk_flags",
            "text",
        ],
        line_rows,
    )

    write_csv(
        report_dir / "818_ROUTE_LIST.csv",
        [
            "file",
            "line",
            "method",
            "path",
        ],
        route_rows,
    )

    write_csv(
        report_dir / "819_RISK_SUMMARY.csv",
        [
            "file",
            "level_support",
            "name_based_hits",
            "network_hits",
            "level_hits",
            "active_hits",
            "risk",
            "reason",
        ],
        risk_rows,
    )

    write_csv(
        report_dir / "820_USER_SCOPE_COUNTS.csv",
        [
            "school_scope",
            "is_active",
            "total",
        ],
        role_counts,
    )

    gate_rows = [
        {
            "check": "db_integrity",
            "result": (
                "PASS"
                if integrity.lower() == "ok"
                else "FAIL"
            ),
            "detail": integrity,
        },
        {
            "check": "db_fk",
            "result": (
                "PASS"
                if fk == 0
                else "FAIL"
            ),
            "detail": str(fk),
        },
        {
            "check": "linked_target_database",
            "result": (
                "PASS"
                if linked_fail == 0
                else "FAIL"
            ),
            "detail": f"fail={linked_fail}/{len(linked_school_rows)}",
        },
        {
            "check": "linked_source_cleanup",
            "result": (
                "PASS"
                if source_fail == 0
                else "FAIL"
            ),
            "detail": f"fail={source_fail}/{len(source_rows)}",
        },
        {
            "check": "multi_level_school_count",
            "result": "INFO",
            "detail": str(len(multi_rows)),
        },
        {
            "check": "source_scan_high_risk_files",
            "result": (
                "REVIEW"
                if high_risk_files
                else "PASS"
            ),
            "detail": str(len(high_risk_files)),
        },
        {
            "check": "source_scan_medium_risk_files",
            "result": "INFO",
            "detail": str(len(medium_risk_files)),
        },
        {
            "check": "V13_12_READY_FOR_UI_FIX_REVIEW",
            "result": (
                "YES"
                if (
                    integrity.lower() == "ok"
                    and fk == 0
                    and linked_fail == 0
                    and source_fail == 0
                )
                else "NO"
            ),
            "detail": (
                "Database sau sáp nhập đạt; dùng source scan để quyết định "
                "có cần vá giao diện/filter liên cấp hay không."
            ),
        },
    ]

    write_csv(
        report_dir / "821_GATE_V13_12.csv",
        ["check", "result", "detail"],
        gate_rows,
    )

    summary = f"""V13.12 - KHẢO SÁT VẬN HÀNH SAU SÁP NHẬP
================================================================================

DATABASE
- integrity = {integrity}
- FK = {fk}
- school_year = {YEAR_CODE}

TRƯỜNG LIÊN CẤP
- linked target fail = {linked_fail}/{len(linked_school_rows)}
- linked source cleanup fail = {source_fail}/{len(source_rows)}
- số trường active đa cấp phát hiện = {len(multi_rows)}

SOURCE SCAN
- files scanned = {len(file_rows)}
- matched source lines = {len(line_rows)}
- routes found = {len(route_rows)}
- HIGH risk files = {len(high_risk_files)}
- MEDIUM risk files = {len(medium_risk_files)}

GHI CHÚ
- HIGH/MEDIUM ở source scan chỉ là cảnh báo tĩnh, chưa khẳng định có lỗi.
- Bước tiếp theo là đọc 819_RISK_SUMMARY.csv và 817_SOURCE_LINES.csv
  để xác định chính xác route/template nào cần sửa.
- V13.12 KHÔNG sửa DB, Plan JSON hay source.

V13_12_READY_FOR_UI_FIX_REVIEW={
    'YES'
    if (
        integrity.lower() == 'ok'
        and fk == 0
        and linked_fail == 0
        and source_fail == 0
    )
    else 'NO'
}
"""

    (
        report_dir / "00_TONG_QUAN_V13_12.txt"
    ).write_text(
        summary,
        encoding="utf-8",
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        for path in sorted(report_dir.iterdir()):
            if path.is_file():
                zf.write(
                    path,
                    arcname=path.name,
                )

    print()
    print("=" * 126)
    print("HOÀN THÀNH V13.12")
    print("=" * 126)
    print(f"DB integrity: {integrity}")
    print(f"DB FK errors: {fk}")
    print(
        f"Linked target DB fail: "
        f"{linked_fail}/{len(linked_school_rows)}"
    )
    print(
        f"Linked source cleanup fail: "
        f"{source_fail}/{len(source_rows)}"
    )
    print(f"Active multi-level schools: {len(multi_rows)}")
    print(f"Source files scanned: {len(file_rows)}")
    print(f"Source matched lines: {len(line_rows)}")
    print(f"Routes found: {len(route_rows)}")
    print(f"HIGH risk source files: {len(high_risk_files)}")
    print(f"MEDIUM risk source files: {len(medium_risk_files)}")
    print(
        "V13_12_READY_FOR_UI_FIX_REVIEW: "
        + (
            "YES"
            if (
                integrity.lower() == "ok"
                and fk == 0
                and linked_fail == 0
                and source_fail == 0
            )
            else "NO"
        )
    )
    print("Database: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")
    print("Source: KHÔNG THAY ĐỔI")
    print(f"ZIP: {zip_path}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.12 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print("Database: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        print("Source: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
