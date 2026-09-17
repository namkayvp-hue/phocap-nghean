from __future__ import annotations

import ast
import hashlib
import json
import os
import py_compile
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"

SERVICE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_level_batch_service.py"
)

MN_RESOLUTION = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_mn_resolution.json"
)

ROSTER_DIR = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
)

MN_ROSTER = (
    ROSTER_DIR
    / "MN_2025_2026.json"
)

EXPECTED_DB_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

EXPECTED_OLD_MN_RESOLUTION_SHA = (
    "cf04df92ed23c734564a13e1ca4d0582"
    "5c2b7fa40ab7112c9cbb10334c15d6aa"
)

EXPECTED_READY = {
    "QD3805-OP-0175",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

OP0337 = "QD3805-OP-0337"
OP0338 = "QD3805-OP-0338"


NEW_FUNCTION = r'''def _precompleted_resolution_status(
    *,
    operation_id: str,
    resolution: dict[str, Any],
    audit_item: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    rule = next(
        (
            dict(x)
            for x in (resolution.get("precompleted") or [])
            if str((x or {}).get("operation_id") or "")
            == str(operation_id or "")
        ),
        None,
    )

    if not rule:
        return None

    raw_source_codes = rule.get("source_school_codes")

    if isinstance(raw_source_codes, (list, tuple)):
        source_codes = [
            str(x or "").strip()
            for x in raw_source_codes
            if str(x or "").strip()
        ]
    else:
        source_code = str(
            rule.get("source_school_code") or ""
        ).strip()

        source_codes = (
            [source_code]
            if source_code
            else []
        )

    target_code = str(
        rule.get("target_school_code") or ""
    ).strip()

    previous_year_code = str(
        rule.get("previous_year_code")
        or "2025-2026"
    )

    current_year_code = str(
        rule.get("current_year_code")
        or "2026-2027"
    )

    if not source_codes or not target_code:
        return {
            "pass": False,
            "operation_id": operation_id,
            "rule": rule,
            "reason": (
                "Rule precompleted thiếu mã "
                "trường nguồn hoặc trường đích."
            ),
        }

    con = engine._connect(read_only=True)

    try:
        target = con.execute(
            """
            SELECT id,code,name,is_active
            FROM schools
            WHERE code=?
            LIMIT 1
            """,
            (target_code,),
        ).fetchone()

        sources = []

        for source_code in source_codes:
            source = con.execute(
                """
                SELECT id,code,name,is_active
                FROM schools
                WHERE code=?
                LIMIT 1
                """,
                (source_code,),
            ).fetchone()

            if source is None:
                return {
                    "pass": False,
                    "operation_id": operation_id,
                    "rule": rule,
                    "reason": (
                        "Không tìm thấy trường nguồn "
                        f"mã {source_code} trong DB."
                    ),
                }

            sources.append(source)

        if target is None:
            return {
                "pass": False,
                "operation_id": operation_id,
                "rule": rule,
                "reason": (
                    "Không tìm thấy trường đích "
                    f"mã {target_code} trong DB."
                ),
            }

        current_source_by_code = {
            code: _active_staff_year_count(
                con,
                school_code=code,
                year_code=current_year_code,
            )
            for code in source_codes
        }

        evidence = {
            "source_school_codes":
                source_codes,

            "source_schools": [
                {
                    "school_id":
                        int(source["id"]),

                    "school_code":
                        str(source["code"] or ""),

                    "school_name":
                        str(source["name"] or ""),

                    "is_active":
                        bool(source["is_active"]),
                }
                for source in sources
            ],

            "target_school_id":
                int(target["id"]),

            "target_school_code":
                str(target["code"] or ""),

            "target_school_name":
                str(target["name"] or ""),

            "target_is_active":
                bool(target["is_active"]),

            "previous_target_active":
                _active_staff_year_count(
                    con,
                    school_code=target_code,
                    year_code=previous_year_code,
                ),

            "current_target_active":
                _active_staff_year_count(
                    con,
                    school_code=target_code,
                    year_code=current_year_code,
                ),

            "current_source_active_by_code":
                current_source_by_code,

            "current_source_active_total":
                sum(
                    int(x or 0)
                    for x in
                    current_source_by_code.values()
                ),
        }

        # Giữ tương thích dữ liệu evidence cũ
        # cho các rule TH chỉ có một nguồn.
        if len(sources) == 1:
            source = sources[0]
            source_code = source_codes[0]

            evidence.update({
                "source_school_id":
                    int(source["id"]),

                "source_school_code":
                    str(source["code"] or ""),

                "source_school_name":
                    str(source["name"] or ""),

                "source_is_active":
                    bool(source["is_active"]),

                "previous_source_active":
                    _active_staff_year_count(
                        con,
                        school_code=source_code,
                        year_code=previous_year_code,
                    ),

                "current_source_active":
                    current_source_by_code[
                        source_code
                    ],
            })

        # Identity exact chỉ bật cho rule yêu cầu.
        identity_evidence = None

        if bool(rule.get("require_identity_exact")):
            year_rows = con.execute(
                """
                SELECT id,code
                FROM school_years
                WHERE code IN (?,?)
                """,
                (
                    previous_year_code,
                    current_year_code,
                ),
            ).fetchall()

            year_ids = {
                str(x["code"]):
                    int(x["id"])
                for x in year_rows
            }

            previous_year_id = year_ids.get(
                previous_year_code
            )

            current_year_id = year_ids.get(
                current_year_code
            )

            if (
                previous_year_id is None
                or current_year_id is None
            ):
                identity_evidence = {
                    "available": False,
                    "reason": (
                        "Không tìm thấy đủ năm học "
                        "để kiểm tra identity."
                    ),
                }
            else:
                origin_ids = [
                    int(target["id"]),
                    *[
                        int(source["id"])
                        for source in sources
                    ],
                ]

                marks = ",".join(
                    "?"
                    for _ in origin_ids
                )

                previous_rows = con.execute(
                    f"""
                    SELECT staff_member_id
                    FROM staff_year_records
                    WHERE school_year_id=?
                      AND school_id IN ({marks})
                      AND is_active=1
                      AND status_code='DANG_LAM_VIEC'
                    """,
                    [
                        previous_year_id,
                        *origin_ids,
                    ],
                ).fetchall()

                current_rows = con.execute(
                    """
                    SELECT staff_member_id
                    FROM staff_year_records
                    WHERE school_year_id=?
                      AND school_id=?
                      AND is_active=1
                    """,
                    (
                        current_year_id,
                        int(target["id"]),
                    ),
                ).fetchall()

                previous_ids = {
                    int(x["staff_member_id"])
                    for x in previous_rows
                }

                current_ids = {
                    int(x["staff_member_id"])
                    for x in current_rows
                }

                identity_evidence = {
                    "available": True,

                    "previous_union_count":
                        len(previous_ids),

                    "current_target_count":
                        len(current_ids),

                    "identity_exact":
                        previous_ids
                        == current_ids,
                }

            evidence["identity"] = (
                identity_evidence
            )

    finally:
        con.close()

    # Năm trước phải dùng đúng tập
    # "đủ điều kiện kế thừa" của V4.3.
    audit = dict(audit_item or {})

    school_checks = [
        dict(x)
        for x in (
            audit.get("school_checks")
            or []
        )
        if isinstance(x, dict)
    ]

    audit_target = next(
        (
            x
            for x in school_checks
            if (
                str(
                    x.get("role") or ""
                ).upper()
                == "TARGET"
                and str(
                    x.get("school_code")
                    or ""
                ).strip()
                == target_code
            )
        ),
        None,
    )

    audit_sources = {}

    for source_code in source_codes:
        item = next(
            (
                x
                for x in school_checks
                if (
                    str(
                        x.get("role") or ""
                    ).upper()
                    == "SOURCE"
                    and str(
                        x.get("school_code")
                        or ""
                    ).strip()
                    == source_code
                )
            ),
            None,
        )

        audit_sources[source_code] = item

    previous_target_eligible = (
        int(
            audit_target.get(
                "active_db_eligible"
            )
            or 0
        )
        if audit_target is not None
        else -1
    )

    previous_source_eligible = {
        code: (
            int(
                item.get(
                    "active_db_eligible"
                )
                or 0
            )
            if item is not None
            else -1
        )
        for code, item
        in audit_sources.items()
    }

    evidence["source_audit_pass"] = bool(
        audit.get("pass")
    )

    evidence[
        "previous_target_eligible"
    ] = previous_target_eligible

    evidence[
        "previous_source_eligible_by_code"
    ] = previous_source_eligible

    # Giữ key cũ cho TH 1 nguồn.
    if len(source_codes) == 1:
        evidence[
            "previous_source_eligible"
        ] = previous_source_eligible[
            source_codes[0]
        ]

    expected_target_previous = int(
        rule.get(
            "expected_previous_target_active"
        )
        or 0
    )

    raw_expected_sources = rule.get(
        "expected_previous_source_active"
    )

    expected_sources = {}

    if isinstance(
        raw_expected_sources,
        dict,
    ):
        expected_sources = {
            str(code): int(value or 0)
            for code, value
            in raw_expected_sources.items()
        }

    elif isinstance(
        raw_expected_sources,
        (list, tuple),
    ):
        if (
            len(raw_expected_sources)
            != len(source_codes)
        ):
            return {
                "pass": False,
                "operation_id":
                    operation_id,
                "rule": rule,
                "evidence":
                    evidence,
                "reason": (
                    "Số expected nguồn "
                    "không khớp số mã nguồn."
                ),
            }

        expected_sources = {
            code: int(
                raw_expected_sources[index]
                or 0
            )
            for index, code
            in enumerate(source_codes)
        }

    elif len(source_codes) == 1:
        expected_sources = {
            source_codes[0]:
                int(
                    raw_expected_sources
                    or 0
                )
        }

    else:
        return {
            "pass": False,
            "operation_id": operation_id,
            "rule": rule,
            "evidence": evidence,
            "reason": (
                "Rule nhiều nguồn phải khai báo "
                "expected_previous_source_active "
                "dạng danh sách hoặc object."
            ),
        }

    expected_current_target = int(
        rule.get(
            "expected_current_target_active"
        )
        or 0
    )

    expected_current_source_total = int(
        rule.get(
            "expected_current_source_active"
        )
        or 0
    )

    checks = {
        "all_sources_inactive":
            all(
                bool(source["is_active"])
                is False
                for source in sources
            ),

        "target_active":
            evidence["target_is_active"]
            is True,

        "source_audit_pass":
            evidence["source_audit_pass"]
            is True,

        "previous_target_eligible":
            previous_target_eligible
            == expected_target_previous,

        "previous_sources_eligible":
            all(
                previous_source_eligible.get(
                    code,
                    -1,
                )
                == expected_sources.get(
                    code,
                    -2,
                )
                for code in source_codes
            ),

        "current_target_active":
            evidence[
                "current_target_active"
            ]
            == expected_current_target,

        "current_sources_active":
            evidence[
                "current_source_active_total"
            ]
            == expected_current_source_total,

        "rollover_sum":
            evidence[
                "current_target_active"
            ]
            == (
                previous_target_eligible
                + sum(
                    previous_source_eligible[
                        code
                    ]
                    for code
                    in source_codes
                )
            ),
    }

    if bool(rule.get("require_identity_exact")):
        identity = dict(
            evidence.get("identity")
            or {}
        )

        expected_identity_count = int(
            rule.get(
                "expected_previous_identity_count"
            )
            or (
                expected_target_previous
                + sum(
                    expected_sources.values()
                )
            )
        )

        checks.update({
            "identity_available":
                bool(
                    identity.get("available")
                )
                is True,

            "previous_identity_count":
                int(
                    identity.get(
                        "previous_union_count"
                    )
                    or -1
                )
                == expected_identity_count,

            "current_identity_count":
                int(
                    identity.get(
                        "current_target_count"
                    )
                    or -1
                )
                == expected_current_target,

            "identity_exact":
                bool(
                    identity.get(
                        "identity_exact"
                    )
                )
                is True,
        })

    return {
        "pass": all(checks.values()),
        "operation_id": operation_id,
        "rule": rule,
        "evidence": evidence,
        "checks": checks,
        "reason": (
            "Nguồn đã khóa; kiểm tra nguồn PASS; "
            "dữ liệu hiện hành tại đích khớp "
            "đúng dấu vết đã hoàn tất trước."
            if all(checks.values())
            else
            "Dấu vết dữ liệu chưa đủ để coi "
            "là đã hoàn tất trước."
        ),
    }
'''


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)

            if not b:
                break

            h.update(b)

    return h.hexdigest()


def atomic_write_text(
    path: Path,
    text: str,
) -> None:
    tmp = path.with_name(
        path.name + ".tmp_qd3805"
    )

    tmp.write_text(
        text,
        encoding="utf-8",
    )

    os.replace(
        tmp,
        path,
    )


def atomic_write_json(
    path: Path,
    payload,
) -> None:
    atomic_write_text(
        path,
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )


def fmt_date(value) -> str:
    s = str(value or "").strip()

    if (
        len(s) >= 10
        and s[4] == "-"
        and s[7] == "-"
    ):
        return (
            s[8:10]
            + "/"
            + s[5:7]
            + "/"
            + s[0:4]
        )

    return s


def position_label(
    group,
    title,
) -> str:

    g = str(
        group or ""
    ).strip().upper()

    if g == "CBQL":
        return "Cán bộ quản lý"

    if g == "GIAO_VIEN":
        return "Giáo viên"

    if g == "NHAN_VIEN":
        return "Nhân viên"

    return str(
        title or group or ""
    ).strip()


def registry_hashes() -> dict[str, str]:
    result = {}

    if ROSTER_DIR.exists():
        for p in sorted(
            ROSTER_DIR.glob("*.json")
        ):
            result[p.name] = sha256(p)

    return result


def backup_state(
    backup_dir: Path,
) -> None:

    service_dst = (
        backup_dir
        / "app"
        / "services"
        / SERVICE.name
    )

    resolution_dst = (
        backup_dir
        / "data"
        / "school_merger_registry"
        / MN_RESOLUTION.name
    )

    roster_dst = (
        backup_dir
        / "data"
        / "school_merger_source_rosters"
    )

    service_dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    resolution_dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    roster_dst.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        SERVICE,
        service_dst,
    )

    shutil.copy2(
        MN_RESOLUTION,
        resolution_dst,
    )

    for p in ROSTER_DIR.glob("*.json"):
        shutil.copy2(
            p,
            roster_dst / p.name,
        )


def restore_state(
    backup_dir: Path,
) -> None:

    service_src = (
        backup_dir
        / "app"
        / "services"
        / SERVICE.name
    )

    resolution_src = (
        backup_dir
        / "data"
        / "school_merger_registry"
        / MN_RESOLUTION.name
    )

    roster_src = (
        backup_dir
        / "data"
        / "school_merger_source_rosters"
    )

    if service_src.exists():
        shutil.copy2(
            service_src,
            SERVICE,
        )

    if resolution_src.exists():
        shutil.copy2(
            resolution_src,
            MN_RESOLUTION,
        )

    ROSTER_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for p in ROSTER_DIR.glob("*.json"):
        p.unlink()

    if roster_src.exists():
        for p in roster_src.glob("*.json"):
            shutil.copy2(
                p,
                ROSTER_DIR / p.name,
            )


def patch_service(
    source: str,
) -> str:

    tree = ast.parse(source)

    node = next(
        (
            n
            for n in tree.body
            if (
                isinstance(
                    n,
                    ast.FunctionDef,
                )
                and n.name
                == "_precompleted_resolution_status"
            )
        ),
        None,
    )

    if node is None:
        raise RuntimeError(
            "Không tìm thấy hàm "
            "_precompleted_resolution_status."
        )

    old_block = "\n".join(
        source.splitlines()[
            node.lineno - 1:
            node.end_lineno
        ]
    )

    required_old_tokens = (
        'rule.get("source_school_code")',
        'expected_previous_source_active',
        '"rollover_sum"',
        'previous_source_eligible',
    )

    for token in required_old_tokens:
        if token not in old_block:
            raise RuntimeError(
                "Nền hàm precompleted "
                "không còn đúng bản đã khảo sát. "
                "Thiếu: "
                + token
            )

    lines = source.splitlines(
        keepends=True
    )

    patched = (
        "".join(
            lines[:node.lineno - 1]
        )
        + NEW_FUNCTION.rstrip()
        + "\n\n"
        + "".join(
            lines[node.end_lineno:]
        )
    )

    ast.parse(patched)

    if (
        "source_school_codes"
        not in patched
        or "require_identity_exact"
        not in patched
    ):
        raise RuntimeError(
            "Patch service chưa đủ marker."
        )

    return patched


def build_mn_dataset(
    db_sha: str,
    generated_at: str,
) -> dict:

    con = sqlite3.connect(
        DB.resolve().as_uri()
        + "?mode=ro",
        uri=True,
    )

    con.row_factory = sqlite3.Row
    con.execute(
        "PRAGMA query_only=ON"
    )

    try:
        year = con.execute(
            """
            SELECT id
            FROM school_years
            WHERE code='2025-2026'
            LIMIT 1
            """
        ).fetchone()

        if year is None:
            raise RuntimeError(
                "Không tìm thấy năm 2025-2026."
            )

        year_id = int(year["id"])

        rows = con.execute(
            """
            SELECT
                syr.id,
                syr.school_id,
                syr.status_code,
                syr.position_group,
                syr.position_title,
                syr.source_status_label,

                sm.ministry_staff_code,
                sm.full_name,
                sm.date_of_birth,
                sm.gender,

                s.name AS school_name,
                c.name AS commune_name

            FROM staff_year_records syr

            JOIN staff_members sm
              ON sm.id=syr.staff_member_id

            JOIN schools s
              ON s.id=syr.school_id

            JOIN communes c
              ON c.id=s.commune_id

            WHERE syr.school_year_id=?
              AND UPPER(
                    TRIM(
                        COALESCE(
                            syr.source_level,
                            ''
                        )
                    )
                  )='MN'

            ORDER BY
                syr.school_id,
                syr.id
            """,
            (year_id,),
        ).fetchall()

    finally:
        con.close()

    output_rows = []

    for index, raw in enumerate(
        rows,
        start=1,
    ):
        r = dict(raw)

        code = str(
            r.get(
                "ministry_staff_code"
            )
            or ""
        ).strip()

        if not code:
            raise RuntimeError(
                "Có dòng MN 2025-2026 "
                "thiếu mã Bộ."
            )

        output_rows.append({
            "excel_row":
                index,

            "commune_name":
                str(
                    r.get(
                        "commune_name"
                    )
                    or ""
                ).strip(),

            "school_name":
                str(
                    r.get(
                        "school_name"
                    )
                    or ""
                ).strip(),

            "staff_code":
                code,

            "full_name":
                str(
                    r.get(
                        "full_name"
                    )
                    or ""
                ).strip(),

            "date_of_birth":
                fmt_date(
                    r.get(
                        "date_of_birth"
                    )
                ),

            "gender":
                str(
                    r.get("gender")
                    or ""
                ).strip(),

            "status_label":
                str(
                    r.get(
                        "source_status_label"
                    )
                    or r.get(
                        "status_code"
                    )
                    or ""
                ).strip(),

            "position_label":
                position_label(
                    r.get(
                        "position_group"
                    ),
                    r.get(
                        "position_title"
                    ),
                ),
        })

    school_count = len({
        (
            row["commune_name"],
            row["school_name"],
        )
        for row in output_rows
    })

    if len(output_rows) != 20472:
        raise RuntimeError(
            "MN snapshot row_count="
            f"{len(output_rows)}, "
            "expected=20472."
        )

    if school_count != 891:
        raise RuntimeError(
            "MN snapshot school_count="
            f"{school_count}, "
            "expected=891."
        )

    return {
        "version": 1,

        "dataset_id":
            "MN-2025-2026-DB-SNAPSHOT",

        "level_code":
            "MN",

        "school_year_code":
            "2025-2026",

        "provenance_type":
            "INTERNAL_DB_SNAPSHOT",

        "source_file":
            (
                "INTERNAL_DB_SNAPSHOT:"
                "phocap.db/"
                "staff_year_records"
            ),

        "source_sha256":
            db_sha,

        "generated_at":
            generated_at,

        "provenance_note":
            (
                "Baseline nội bộ được đóng băng "
                "từ staff_year_records năm "
                "2025-2026 do chưa có file "
                "danh sách đội ngũ MN độc lập. "
                "Không được mô tả là nguồn Excel "
                "độc lập."
            ),

        "row_count":
            len(output_rows),

        "school_count":
            school_count,

        "active_status_labels": [
            "Đang làm việc",
            "Chuyển đến",
        ],

        "rows":
            output_rows,
    }


def update_resolution(
    payload: dict,
) -> dict:

    if (
        str(
            payload.get("schema")
            or ""
        )
        != "QD3805_MN_RESOLUTION_2026"
    ):
        raise RuntimeError(
            "MN resolution sai schema."
        )

    result = dict(payload)

    principles = list(
        result.get("principles")
        or []
    )

    principle = (
        "Phương án đã hoàn tất trước có "
        "nhiều trường nguồn chỉ được nhận "
        "DONE khi tất cả nguồn đã khóa, "
        "audit PASS và dấu vết identity "
        "năm hiện hành khớp dữ liệu kế thừa."
    )

    if principle not in principles:
        principles.append(
            principle
        )

    result["principles"] = principles

    pre = [
        dict(x)
        for x in (
            result.get("precompleted")
            or []
        )
        if isinstance(x, dict)
    ]

    if any(
        str(
            x.get("operation_id")
            or ""
        )
        == OP0337
        for x in pre
    ):
        raise RuntimeError(
            "OP-0337 đã tồn tại "
            "trong precompleted; dừng."
        )

    pre.append({
        "operation_id":
            "QD3805-OP-0337",

        "source_school_codes": [
            "40429325",
            "40429332",
        ],

        "target_school_code":
            "40429310",

        "previous_year_code":
            "2025-2026",

        "current_year_code":
            "2026-2027",

        "expected_previous_target_active":
            29,

        "expected_previous_source_active": [
            25,
            33,
        ],

        "expected_current_target_active":
            87,

        "expected_current_source_active":
            0,

        "expected_previous_identity_count":
            87,

        "require_identity_exact":
            True,

        "reason": (
            "MN Nghi Hoa và MN Nghi Vạn "
            "đã inactive; audit nguồn PASS; "
            "87 staff_member_id tại MN Nghi Diên "
            "năm 2026-2027 khớp 100% với "
            "29 Nghi Diên + 25 Nghi Hoa "
            "+ 33 Nghi Vạn đủ điều kiện "
            "năm 2025-2026. Không chạy lại."
        ),
    })

    result["precompleted"] = pre

    return result


PREVIEW_CHILD = r'''
import json
import sys

from app.services.school_merger_level_batch_service import (
    build_level_batch_preview,
)

from app.services.school_merger_source_audit_service import (
    source_registry_summary,
)

level = sys.argv[1]

preview = build_level_batch_preview(
    school_year_id=2,
    level_code=level,
)

states = {}

for row in preview.get("rows") or []:
    if not isinstance(row, dict):
        continue

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    ).strip()

    state = str(
        row.get(
            "batch_state"
        )
        or ""
    ).strip().upper()

    if op:
        states[op] = state

out = {
    "level":
        level,

    "counts":
        preview.get("counts")
        or {},

    "candidate_count":
        preview.get(
            "candidate_count"
        ),

    "effective_block_count":
        preview.get(
            "effective_block_count"
        ),

    "ready_for_execution":
        preview.get(
            "ready_for_execution"
        ),

    "extra_blockers":
        preview.get(
            "extra_blockers"
        )
        or [],

    "states":
        states,

    "registry_summary":
        source_registry_summary(),
}

print(
    json.dumps(
        out,
        ensure_ascii=True,
        default=str,
    )
)
'''


def run_preview(
    level: str,
) -> dict:

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            PREVIEW_CHILD,
            level,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)

        raise RuntimeError(
            f"Preview {level} bị lỗi."
        )

    return json.loads(
        proc.stdout.strip()
    )


def main() -> None:

    print("=" * 120)
    print(
        "CAI DAT CHINH THUC ROSTER MN "
        "+ PRECOMPLETED OP-0337"
    )
    print("=" * 120)
    print()
    print(
        "KHONG THUC HIEN SAP NHAP."
    )
    print(
        "KHONG GHI PHOCAP.DB."
    )
    print(
        "KHONG MO KHOA NGHI HOA / NGHI VAN."
    )
    print("=" * 120)

    if not DB.exists():
        raise RuntimeError(
            "Không tìm thấy DB."
        )

    if not SERVICE.exists():
        raise RuntimeError(
            "Không tìm thấy batch service."
        )

    if not MN_RESOLUTION.exists():
        raise RuntimeError(
            "Không tìm thấy MN resolution."
        )

    ROSTER_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    db_before = sha256(DB)

    service_before_sha = sha256(
        SERVICE
    )

    resolution_before_sha = sha256(
        MN_RESOLUTION
    )

    roster_before = registry_hashes()

    print()
    print(
        "DB SHA trước        :",
        db_before,
    )

    print(
        "Batch service SHA   :",
        service_before_sha,
    )

    print(
        "MN resolution SHA   :",
        resolution_before_sha,
    )

    if db_before != EXPECTED_DB_SHA:
        raise RuntimeError(
            "DỪNG: DB SHA không đúng "
            "nền vừa dry-run."
        )

    if (
        resolution_before_sha
        != EXPECTED_OLD_MN_RESOLUTION_SHA
    ):
        raise RuntimeError(
            "DỪNG: MN resolution "
            "đã thay đổi ngoài dự kiến."
        )

    if MN_ROSTER.exists():
        raise RuntimeError(
            "DỪNG: MN_2025_2026.json "
            "đã tồn tại trước cài."
        )

    # --------------------------------------------------------
    # Baseline preview.
    # --------------------------------------------------------

    print()
    print("=" * 120)
    print("PREVIEW TRUOC CAI")
    print("=" * 120)

    before_mn = run_preview("MN")
    before_th = run_preview("TH")

    print(
        "MN:",
        before_mn["counts"],
    )

    print(
        "TH:",
        before_th["counts"],
    )

    # --------------------------------------------------------
    # Build candidate files.
    # --------------------------------------------------------

    generated_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    dataset = build_mn_dataset(
        db_before,
        generated_at,
    )

    source_text = SERVICE.read_text(
        encoding="utf-8-sig",
    )

    patched_source = patch_service(
        source_text
    )

    current_resolution = json.loads(
        MN_RESOLUTION.read_text(
            encoding="utf-8-sig",
        )
    )

    patched_resolution = (
        update_resolution(
            current_resolution
        )
    )

    # Validate JSON before touching real files.
    json.loads(
        json.dumps(
            dataset,
            ensure_ascii=False,
        )
    )

    json.loads(
        json.dumps(
            patched_resolution,
            ensure_ascii=False,
        )
    )

    ast.parse(
        patched_source
    )

    # --------------------------------------------------------
    # Backup.
    # --------------------------------------------------------

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_dir = (
        ROOT
        / "backups"
        / (
            "backup_truoc_roster_MN_"
            "precompleted_OP0337_"
            + stamp
        )
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_state(
        backup_dir
    )

    print()
    print(
        "Backup:",
        backup_dir,
    )

    installed = False

    try:
        # ----------------------------------------------------
        # Write official roster.
        # ----------------------------------------------------

        atomic_write_json(
            MN_ROSTER,
            dataset,
        )

        loaded_dataset = json.loads(
            MN_ROSTER.read_text(
                encoding="utf-8"
            )
        )

        if (
            loaded_dataset.get(
                "dataset_id"
            )
            != "MN-2025-2026-DB-SNAPSHOT"
        ):
            raise RuntimeError(
                "Roster MN ghi ra sai dataset_id."
            )

        if (
            int(
                loaded_dataset.get(
                    "row_count"
                )
                or 0
            )
            != 20472
        ):
            raise RuntimeError(
                "Roster MN sai row_count."
            )

        # ----------------------------------------------------
        # Patch service.
        # ----------------------------------------------------

        atomic_write_text(
            SERVICE,
            patched_source,
        )

        py_compile.compile(
            str(SERVICE),
            doraise=True,
        )

        # ----------------------------------------------------
        # Write resolution.
        # ----------------------------------------------------

        atomic_write_json(
            MN_RESOLUTION,
            patched_resolution,
        )

        # ----------------------------------------------------
        # DB must still be untouched.
        # ----------------------------------------------------

        if sha256(DB) != db_before:
            raise RuntimeError(
                "DỪNG: DB thay đổi "
                "trong lúc cài."
            )

        # ----------------------------------------------------
        # Natural preview after installation.
        # ----------------------------------------------------

        print()
        print("=" * 120)
        print("HAU KIEM SAU CAI")
        print("=" * 120)

        after_mn = run_preview("MN")
        after_th = run_preview("TH")

        print(
            "MN:",
            after_mn["counts"],
        )

        print(
            "candidate_count       =",
            after_mn.get(
                "candidate_count"
            ),
        )

        print(
            "effective_block_count =",
            after_mn.get(
                "effective_block_count"
            ),
        )

        states = (
            after_mn.get("states")
            or {}
        )

        print()
        print(
            "OP-0337 =",
            states.get(OP0337),
        )

        for op in sorted(
            EXPECTED_READY
        ):
            print(
                op,
                "=",
                states.get(op),
            )

        print(
            "OP-0338 =",
            states.get(OP0338),
        )

        expected_counts = {
            "KEEP": 51,
            "DONE": 183,
            "READY": 5,
            "BLOCK": 1,
        }

        if (
            after_mn.get("counts")
            != expected_counts
        ):
            raise RuntimeError(
                "MN KPI sau cài "
                "không đúng kỳ vọng: "
                + repr(
                    after_mn.get(
                        "counts"
                    )
                )
            )

        if (
            after_mn.get(
                "candidate_count"
            )
            != 5
        ):
            raise RuntimeError(
                "candidate_count != 5."
            )

        if (
            after_mn.get(
                "effective_block_count"
            )
            != 2
        ):
            raise RuntimeError(
                "effective_block_count != 2."
            )

        if states.get(OP0337) != "DONE":
            raise RuntimeError(
                "OP-0337 chưa DONE."
            )

        if states.get(OP0338) != "BLOCK":
            raise RuntimeError(
                "OP-0338 không còn BLOCK."
            )

        for op in EXPECTED_READY:
            if (
                states.get(op)
                != "READY"
            ):
                raise RuntimeError(
                    f"{op} chưa READY."
                )

        # TH must be exactly unchanged.
        th_compare_keys = (
            "counts",
            "candidate_count",
            "effective_block_count",
            "ready_for_execution",
        )

        for key in th_compare_keys:
            if (
                before_th.get(key)
                != after_th.get(key)
            ):
                raise RuntimeError(
                    "TH thay đổi ngoài dự kiến "
                    f"tại {key}: "
                    f"{before_th.get(key)} "
                    f"-> {after_th.get(key)}"
                )

        # Registry summary must contain MN official.
        summary = (
            after_mn.get(
                "registry_summary"
            )
            or {}
        )

        datasets = (
            summary.get("datasets")
            or []
        )

        mn_item = next(
            (
                x
                for x in datasets
                if (
                    str(
                        x.get(
                            "dataset_id"
                        )
                        or ""
                    )
                    == "MN-2025-2026-DB-SNAPSHOT"
                )
            ),
            None,
        )

        if mn_item is None:
            raise RuntimeError(
                "Source audit không thấy "
                "MN official dataset."
            )

        if (
            int(
                mn_item.get(
                    "row_count"
                )
                or 0
            )
            != 20472
        ):
            raise RuntimeError(
                "MN official dataset "
                "không có 20472 rows."
            )

        # Final DB safety.
        db_after = sha256(DB)

        if db_after != db_before:
            raise RuntimeError(
                "DB SHA thay đổi "
                "ngoài dự kiến."
            )

        installed = True

        report_dir = (
            ROOT
            / "exports"
            / "Cai_roster_MN_OP0337"
        )

        report_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        report_path = (
            report_dir
            / (
                "ket_qua_cai_roster_MN_"
                "OP0337_"
                + stamp
                + ".json"
            )
        )

        report = {
            "status":
                "SUCCESS",

            "database_changed":
                False,

            "db_sha256":
                db_after,

            "roster_file":
                str(MN_ROSTER),

            "roster_sha256":
                sha256(MN_ROSTER),

            "roster_dataset_id":
                dataset["dataset_id"],

            "roster_provenance_type":
                dataset[
                    "provenance_type"
                ],

            "roster_rows":
                dataset["row_count"],

            "roster_schools":
                dataset[
                    "school_count"
                ],

            "service_sha256_before":
                service_before_sha,

            "service_sha256_after":
                sha256(SERVICE),

            "resolution_sha256_before":
                resolution_before_sha,

            "resolution_sha256_after":
                sha256(MN_RESOLUTION),

            "mn_before":
                before_mn,

            "mn_after":
                after_mn,

            "th_before":
                before_th,

            "th_after":
                after_th,

            "backup":
                str(backup_dir),

            "note":
                (
                    "Không thực hiện sáp nhập. "
                    "Không mở khóa nguồn. "
                    "OP-0337 chỉ được nhận DONE "
                    "qua precompleted evidence."
                ),
        }

        atomic_write_json(
            report_path,
            report,
        )

        print()
        print("=" * 120)
        print("CAI DAT THANH CONG")
        print("=" * 120)

        print(
            "MN roster :",
            MN_ROSTER,
        )

        print(
            "Dataset   :",
            dataset["dataset_id"],
        )

        print(
            "Nguon     : INTERNAL_DB_SNAPSHOT"
        )

        print(
            "Rows      :",
            dataset["row_count"],
        )

        print(
            "Schools   :",
            dataset["school_count"],
        )

        print()
        print(
            "MN KPI    :",
            after_mn["counts"],
        )

        print(
            "Candidate :",
            after_mn[
                "candidate_count"
            ],
        )

        print(
            "Eff block :",
            after_mn[
                "effective_block_count"
            ],
        )

        print()
        print(
            "OP-0337   : DONE - "
            "KHONG CHAY LAI"
        )

        print(
            "OP-0338   : BLOCK"
        )

        print(
            "Luong Minh: VAN CHAN"
        )

        print()
        print(
            "TH        : KHONG THAY DOI"
        )

        print(
            "Database  : KHONG THAY DOI"
        )

        print(
            "DB SHA    :",
            db_after,
        )

        print()
        print(
            "Backup    :",
            backup_dir,
        )

        print(
            "Report    :",
            report_path,
        )

        print("=" * 120)

    except Exception:
        print()
        print("=" * 120)
        print(
            "CAI DAT LOI - DANG KHOI PHUC FILE"
        )
        print("=" * 120)

        restore_state(
            backup_dir
        )

        # DB was never supposed to change.
        db_now = sha256(DB)

        print(
            "DB SHA sau rollback file:",
            db_now,
        )

        if db_now != db_before:
            print(
                "CANH BAO NGHIEM TRONG: "
                "DB DA THAY DOI."
            )

        else:
            print(
                "Database: KHONG THAY DOI"
            )

        print(
            "Source/Resolution/Registry: "
            "DA KHOI PHUC TU BACKUP"
        )

        raise


if __name__ == "__main__":
    main()
