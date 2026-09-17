from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


sys.dont_write_bytecode = True

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

LOCK = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_level_lock.json"
)

ROSTER = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
    / "THCS_2025_2026.json"
)

RESOLUTION = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_thcs_resolution.json"
)

HISTORY = (
    ROOT
    / "data"
    / "school_merger_approved_plans.json"
)


EXPECTED = {
    "db":
        "882e4925fd3e39d7e097ce127612c093"
        "852075e608d3f937294135282afec75a",

    "service":
        "963b8d6a280d8abef8e96486abd87d77"
        "cea289b08d2edb497647f250ed1b2af8",

    "lock":
        "ad310048a4c5b239404e0902cc04fda1"
        "d73474d11a739a2ca009d2727e4390c3",

    "roster":
        "926528e0ae600a6b950b459c6f8ec5c"
        "6810e69d49158d1ff3c9a3d76c0bca657",

    "history":
        "4e2c5f044c48c57dda40fecc11f4e9f"
        "466f236aacc082f224536b1685cadb1fc",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=90,
    )

    con.row_factory = sqlite3.Row

    con.execute(
        "PRAGMA query_only=ON"
    )

    con.execute(
        "PRAGMA foreign_keys=ON"
    )

    return con


def find_function(
    tree: ast.Module,
    name: str,
) -> ast.FunctionDef:

    found = [
        node
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name == name
    ]

    if len(found) != 1:
        raise RuntimeError(
            f"Phai tim thay dung 1 ham {name}, "
            f"nhung tim thay {len(found)}."
        )

    return found[0]


def find_assignment(
    tree: ast.Module,
    name: str,
):

    result = []

    for node in tree.body:

        if isinstance(
            node,
            ast.Assign,
        ):
            for target in node.targets:
                if (
                    isinstance(
                        target,
                        ast.Name,
                    )
                    and target.id == name
                ):
                    result.append(node)

        elif isinstance(
            node,
            ast.AnnAssign,
        ):
            target = node.target

            if (
                isinstance(
                    target,
                    ast.Name,
                )
                and target.id == name
            ):
                result.append(node)

    if len(result) != 1:
        raise RuntimeError(
            f"Phai tim thay dung 1 bien {name}, "
            f"nhung tim thay {len(result)}."
        )

    return result[0]


print("=" * 138)
print("CAI RESOLUTION THCS - BUOC 1 V3 AST")
print("NGHI HUONG GIU NGUYEN + 2 NGHI LOC PRECOMPLETED")
print("=" * 138)

print("KHONG GHI DATABASE.")
print("KHONG CHAY SAP NHAP THCS.")


# ============================================================
# 1. SERVER / WAL
# ============================================================

print()
print("=" * 138)
print("1. SERVER / WAL GATE")
print("=" * 138)


for suffix in (
    "-wal",
    "-journal",
):

    path = Path(
        str(DB) + suffix
    )

    size = (
        path.stat().st_size
        if path.exists()
        else 0
    )

    print(
        path.name,
        "=",
        size,
    )

    if size > 0:
        raise RuntimeError(
            "DUNG: Uvicorn/server chua dung hoan toan."
        )


# ============================================================
# 2. HASH GATE
# ============================================================

print()
print("=" * 138)
print("2. HASH GATE")
print("=" * 138)


before = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "roster":
        sha256(ROSTER),

    "history":
        sha256(HISTORY),
}


for key, value in before.items():

    print(
        f"{key:12s} = {value}"
    )

    if value != EXPECTED[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


if RESOLUTION.exists():

    print(
        "RESOLUTION DA TON TAI =",
        RESOLUTION,
    )

    print(
        "SHA =",
        sha256(RESOLUTION),
    )

    raise RuntimeError(
        "DUNG: khong ghi de resolution THCS."
    )


# ============================================================
# 3. DB HEALTH
# ============================================================

con = connect_ro()

try:

    integrity = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    fk = len(
        con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    )


    print()
    print("=" * 138)
    print("3. DATABASE HEALTH")
    print("=" * 138)

    print(
        "integrity =",
        integrity,
    )

    print(
        "FK        =",
        fk,
    )


    if (
        integrity.lower() != "ok"
        or fk != 0
    ):
        raise RuntimeError(
            "DUNG: database health FAIL."
        )


    nghi_huong = con.execute(
        """
        SELECT
            id,
            code,
            name,
            commune_id,
            is_active
        FROM schools
        WHERE id=?
          AND TRIM(code)=?
        """,
        (
            1408,
            "40413505",
        ),
    ).fetchone()


    print()
    print("=" * 138)
    print("4. THCS NGHI HUONG")
    print("=" * 138)

    print(
        json.dumps(
            dict(nghi_huong)
            if nghi_huong
            else None,
            ensure_ascii=False,
        )
    )


    if nghi_huong is None:
        raise RuntimeError(
            "DUNG: khong tim thay THCS Nghi Huong."
        )


    if not bool(
        nghi_huong["is_active"]
    ):
        raise RuntimeError(
            "DUNG: THCS Nghi Huong khong active."
        )


finally:
    con.close()


# ============================================================
# 4. RESOLUTION
# ============================================================

resolution_payload = {
    "schema":
        "QD3805_THCS_RESOLUTION_2026",

    "level_code":
        "THCS",

    "effective_school_year":
        "2026-2027",

    "principles": [
        (
            "Chỉ dùng QĐ3805 và năm hiệu lực 2026-2027."
        ),
        (
            "Không sửa dữ liệu lịch sử các năm cũ."
        ),
        (
            "Phương án đã hoàn tất trước được nhận DONE "
            "và tuyệt đối không chạy lại."
        ),
        (
            "THCS Nghi Hương mã 40413505 được xác nhận "
            "GIỮ NGUYÊN do dòng QĐ3805 thiếu chữ Giữ nguyên."
        ),
        (
            "Tách điểm, tiếp nhận điểm, liên cấp hoặc "
            "phương án chưa đủ nguồn-đích không ép vào batch thuần."
        ),
    ],

    "rename_only": [],

    "special_same_level": [],

    "precompleted": [
        {
            "operation_id":
                "QD3805-OP-0342",

            "evidence_mode":
                "HISTORY_CLOSED_STATE",

            "history_plan_id":
                "QD3805-NGHI-LOC-THCS-NGHI-DIEN",

            "source_school_id":
                1608,

            "source_school_code":
                "40429532",

            "source_school_name":
                "THCS Nghi Vạn",

            "target_school_id":
                1605,

            "target_school_code":
                "40429510",

            "target_school_name":
                "THCS Nghi Diên",

            "reason":
                (
                    "Đã hoàn tất trước. "
                    "Lịch sử COMPLETED xác nhận "
                    "Nghi Vạn -> Nghi Diên; "
                    "nguồn đã inactive và trạng thái dữ liệu đã đóng. "
                    "Không chạy lại."
                ),
        },

        {
            "operation_id":
                "QD3805-OP-0343",

            "evidence_mode":
                "HISTORY_CLOSED_STATE",

            "history_plan_id":
                "QD3805-NGHI-LOC-THCS-NGHI-TRUNG",

            "source_school_id":
                1607,

            "source_school_code":
                "40429525",

            "source_school_name":
                "THCS Nghi Hoa",

            "target_school_id":
                1606,

            "target_school_code":
                "40429523",

            "target_school_name":
                "THCS Nghi Trung",

            "reason":
                (
                    "Đã hoàn tất trước. "
                    "Lịch sử COMPLETED xác nhận "
                    "Nghi Hoa -> Nghi Trung; "
                    "nguồn đã inactive và trạng thái dữ liệu đã đóng. "
                    "Không chạy lại."
                ),
        },
    ],

    "deferred_orphans": [
        {
            "operation_id":
                "QD3805-ORPHAN-R116",

            "excel_row":
                116,

            "stt":
                110,

            "commune":
                "Cửa Lò",

            "school":
                "THCS Nghi Hương",

            "school_id":
                1408,

            "school_code":
                "40413505",

            "confirmed_keep":
                True,

            "status":
                "GIỮ NGUYÊN – KHÔNG TÁC ĐỘNG",

            "display_title":
                "THCS Nghi Hương – GIỮ NGUYÊN",

            "reason":
                (
                    "Đã xác nhận nghiệp vụ: "
                    "dòng QĐ3805 thiếu chữ 'Giữ nguyên'. "
                    "Giữ nguyên school_id=1408, mã 40413505 "
                    "và toàn bộ dữ liệu."
                ),
        }
    ],
}


# ============================================================
# 5. ĐỌC SOURCE + AST
# ============================================================

original = SERVICE.read_text(
    encoding="utf-8"
)

tree = ast.parse(
    original,
    filename=str(SERVICE),
)


resolution_node = find_function(
    tree,
    "_resolution_context",
)

precompleted_node = find_function(
    tree,
    "_precompleted_resolution_status",
)

mn_path_node = find_assignment(
    tree,
    "MN_RESOLUTION_PATH",
)


print()
print("=" * 138)
print("5. AST SOURCE MAP")
print("=" * 138)

print(
    "_resolution_context =",
    resolution_node.lineno,
    "->",
    resolution_node.end_lineno,
)

print(
    "_precompleted_resolution_status =",
    precompleted_node.lineno,
    "->",
    precompleted_node.end_lineno,
)

print(
    "MN_RESOLUTION_PATH =",
    mn_path_node.lineno,
    "->",
    mn_path_node.end_lineno,
)


if (
    "THCS_RESOLUTION_PATH"
    in original
):
    raise RuntimeError(
        "DUNG: source da co THCS_RESOLUTION_PATH bat ngo."
    )


# ============================================================
# 6. HÀM _resolution_context MỚI
# ============================================================

NEW_RESOLUTION_CONTEXT = r'''def _resolution_context(level_code: str) -> dict[str, Any]:
    level = _level(level_code)

    if level == "TH":
        payload, fingerprint = _load_resolution_file(
            TH_RESOLUTION_PATH,
            "Tiểu học",
        )

    elif level == "MN":
        payload, fingerprint = _load_resolution_file(
            MN_RESOLUTION_PATH,
            "Mầm non",
        )

    elif level == "THCS":
        payload, fingerprint = _load_resolution_file(
            THCS_RESOLUTION_PATH,
            "THCS",
        )

    else:
        payload, fingerprint = {}, ""

    return {
        "payload": payload,
        "fingerprint": fingerprint,
        "rename_only": [
            dict(x)
            for x in (payload.get("rename_only") or [])
            if isinstance(x, dict)
        ],
        "special_same_level": [
            dict(x)
            for x in (payload.get("special_same_level") or [])
            if isinstance(x, dict)
        ],
        "precompleted": [
            dict(x)
            for x in (payload.get("precompleted") or [])
            if isinstance(x, dict)
        ],
        "deferred_orphans": [
            dict(x)
            for x in (payload.get("deferred_orphans") or [])
            if isinstance(x, dict)
        ],
    }
'''


# ============================================================
# 7. HÀM PRECOMPLETED MỚI
# ============================================================

NEW_PRECOMPLETED = r'''def _precompleted_resolution_status(
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

    evidence_mode = str(
        rule.get("evidence_mode") or ""
    ).strip().upper()

    # ========================================================
    # THCS: phương án đã thực hiện trước.
    # Không phụ thuộc roster source hiện tại.
    # Phải khớp đồng thời:
    # - plan lịch sử COMPLETED;
    # - source/target ID + code chính xác;
    # - source inactive;
    # - target active;
    # - source không còn dữ liệu CURRENT/FUTURE;
    # - source không còn user active.
    # ========================================================

    if evidence_mode == "HISTORY_CLOSED_STATE":

        source_code = str(
            rule.get("source_school_code") or ""
        ).strip()

        target_code = str(
            rule.get("target_school_code") or ""
        ).strip()

        expected_source_id = int(
            rule.get("source_school_id") or 0
        )

        expected_target_id = int(
            rule.get("target_school_id") or 0
        )

        history_plan_id = str(
            rule.get("history_plan_id") or ""
        ).strip()


        con = engine._connect(
            read_only=True
        )

        try:

            source = con.execute(
                """
                SELECT
                    id,
                    code,
                    name,
                    is_active
                FROM schools
                WHERE code=?
                LIMIT 1
                """,
                (source_code,),
            ).fetchone()


            target = con.execute(
                """
                SELECT
                    id,
                    code,
                    name,
                    is_active
                FROM schools
                WHERE code=?
                LIMIT 1
                """,
                (target_code,),
            ).fetchone()


            if (
                source is None
                or target is None
            ):
                return {
                    "pass": False,
                    "operation_id": operation_id,
                    "rule": rule,
                    "reason": (
                        "Không tìm thấy đủ trường nguồn/đích "
                        "theo mã của phương án đã hoàn tất trước."
                    ),
                }


            source_id = int(
                source["id"]
            )

            target_id = int(
                target["id"]
            )


            active_source_users = int(
                con.execute(
                    """
                    SELECT COUNT(*)
                    FROM users
                    WHERE school_id=?
                      AND is_active=1
                    """,
                    (source_id,),
                ).fetchone()[0]
                or 0
            )


            year_rows = con.execute(
                """
                SELECT id,code
                FROM school_years
                WHERE code IN (
                    '2026-2027',
                    '2027-2028'
                )
                """
            ).fetchall()


            move_year_ids = [
                int(x["id"])
                for x in year_rows
            ]


            residual = {}


            table_rows = con.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()


            for table_row in table_rows:

                table_name = str(
                    table_row["name"]
                )

                qtable = (
                    '"'
                    + table_name.replace(
                        '"',
                        '""',
                    )
                    + '"'
                )


                cols = {
                    str(x["name"])
                    for x in con.execute(
                        f"PRAGMA table_info({qtable})"
                    ).fetchall()
                }


                if not {
                    "school_id",
                    "school_year_id",
                }.issubset(cols):
                    continue


                if not move_year_ids:
                    continue


                marks = ",".join(
                    "?"
                    for _ in move_year_ids
                )


                n = int(
                    con.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM {qtable}
                        WHERE school_id=?
                          AND school_year_id
                              IN ({marks})
                        """,
                        [
                            source_id,
                            *move_year_ids,
                        ],
                    ).fetchone()[0]
                    or 0
                )


                if n:
                    residual[
                        table_name
                    ] = n


        finally:
            con.close()


        history_path = (
            PROJECT_DIR
            / "data"
            / "school_merger_approved_plans.json"
        )


        try:

            history_payload = json.loads(
                history_path.read_text(
                    encoding="utf-8-sig"
                )
            )

        except Exception as exc:

            return {
                "pass": False,
                "operation_id": operation_id,
                "rule": rule,
                "reason": (
                    "Không đọc được lịch sử sáp nhập: "
                    + str(exc)
                ),
            }


        history_match = None


        for raw in (
            history_payload.get("plans")
            or []
        ):

            if not isinstance(
                raw,
                dict,
            ):
                continue


            if str(
                raw.get("id")
                or ""
            ) == history_plan_id:

                history_match = dict(raw)
                break


        history_sources = []
        history_target = 0
        history_completed = False


        if history_match is not None:

            history_sources = sorted(
                int(x)
                for x in (
                    history_match.get(
                        "source_school_ids"
                    )
                    or []
                )
            )


            history_target = int(
                history_match.get(
                    "target_school_id"
                )
                or 0
            )


            history_completed = (
                str(
                    history_match.get(
                        "status"
                    )
                    or ""
                ).upper()
                == "COMPLETED"
            )


        checks = {
            "history_found":
                history_match is not None,

            "history_completed":
                history_completed,

            "history_source_exact":
                history_sources
                == [expected_source_id],

            "history_target_exact":
                history_target
                == expected_target_id,

            "source_id_exact":
                source_id
                == expected_source_id,

            "target_id_exact":
                target_id
                == expected_target_id,

            "source_inactive":
                bool(
                    source["is_active"]
                )
                is False,

            "target_active":
                bool(
                    target["is_active"]
                )
                is True,

            "source_current_future_residual_zero":
                not bool(residual),

            "active_source_users_zero":
                active_source_users
                == 0,
        }


        passed = all(
            checks.values()
        )


        return {
            "pass":
                passed,

            "operation_id":
                operation_id,

            "rule":
                rule,

            "evidence_mode":
                evidence_mode,

            "evidence": {
                "source_school_id":
                    source_id,

                "source_school_code":
                    str(
                        source["code"]
                        or ""
                    ),

                "source_school_name":
                    str(
                        source["name"]
                        or ""
                    ),

                "source_is_active":
                    bool(
                        source["is_active"]
                    ),

                "target_school_id":
                    target_id,

                "target_school_code":
                    str(
                        target["code"]
                        or ""
                    ),

                "target_school_name":
                    str(
                        target["name"]
                        or ""
                    ),

                "target_is_active":
                    bool(
                        target["is_active"]
                    ),

                "history_plan_id":
                    history_plan_id,

                "history_source_ids":
                    history_sources,

                "history_target_id":
                    history_target,

                "active_source_users":
                    active_source_users,

                "source_current_future_residual":
                    residual,
            },

            "checks":
                checks,

            "reason": (
                "Lịch sử COMPLETED và trạng thái DB "
                "xác nhận phương án đã hoàn tất trước; "
                "không chạy lại."
                if passed
                else
                "Dấu vết lịch sử/trạng thái DB chưa đủ "
                "để coi phương án đã hoàn tất trước."
            ),
        }


    # ========================================================
    # CƠ CHẾ PRECOMPLETED CŨ CỦA TH/MN.
    # Giữ nguyên logic trước đây.
    # ========================================================

    source_code = str(
        rule.get("source_school_code")
        or ""
    ).strip()

    target_code = str(
        rule.get("target_school_code")
        or ""
    ).strip()

    previous_year_code = str(
        rule.get("previous_year_code")
        or "2025-2026"
    )

    current_year_code = str(
        rule.get("current_year_code")
        or "2026-2027"
    )


    con = engine._connect(
        read_only=True
    )

    try:

        source = con.execute(
            """
            SELECT id,code,name,is_active
            FROM schools
            WHERE code=?
            LIMIT 1
            """,
            (source_code,),
        ).fetchone()


        target = con.execute(
            """
            SELECT id,code,name,is_active
            FROM schools
            WHERE code=?
            LIMIT 1
            """,
            (target_code,),
        ).fetchone()


        if (
            source is None
            or target is None
        ):
            return {
                "pass": False,
                "operation_id": operation_id,
                "reason": (
                    "Không tìm thấy đủ trường "
                    "nguồn/đích theo mã trong DB."
                ),
            }


        evidence = {
            "source_school_id":
                int(source["id"]),

            "source_school_code":
                str(source["code"] or ""),

            "source_school_name":
                str(source["name"] or ""),

            "source_is_active":
                bool(source["is_active"]),

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

            "previous_source_active":
                _active_staff_year_count(
                    con,
                    school_code=source_code,
                    year_code=previous_year_code,
                ),

            "current_target_active":
                _active_staff_year_count(
                    con,
                    school_code=target_code,
                    year_code=current_year_code,
                ),

            "current_source_active":
                _active_staff_year_count(
                    con,
                    school_code=source_code,
                    year_code=current_year_code,
                ),
        }

    finally:
        con.close()


    audit = dict(
        audit_item
        or {}
    )


    school_checks = [
        dict(x)
        for x in (
            audit.get(
                "school_checks"
            )
            or []
        )
        if isinstance(
            x,
            dict,
        )
    ]


    audit_target = next(
        (
            x
            for x in school_checks
            if str(
                x.get("role")
                or ""
            ).upper()
            == "TARGET"
            and str(
                x.get("school_code")
                or ""
            ).strip()
            == target_code
        ),
        None,
    )


    audit_source = next(
        (
            x
            for x in school_checks
            if str(
                x.get("role")
                or ""
            ).upper()
            == "SOURCE"
            and str(
                x.get("school_code")
                or ""
            ).strip()
            == source_code
        ),
        None,
    )


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


    previous_source_eligible = (
        int(
            audit_source.get(
                "active_db_eligible"
            )
            or 0
        )
        if audit_source is not None
        else -1
    )


    evidence[
        "source_audit_pass"
    ] = bool(
        audit.get("pass")
    )

    evidence[
        "previous_target_eligible"
    ] = previous_target_eligible

    evidence[
        "previous_source_eligible"
    ] = previous_source_eligible


    expected = {
        "previous_target_active":
            int(
                rule.get(
                    "expected_previous_target_active"
                )
                or 0
            ),

        "previous_source_active":
            int(
                rule.get(
                    "expected_previous_source_active"
                )
                or 0
            ),

        "current_target_active":
            int(
                rule.get(
                    "expected_current_target_active"
                )
                or 0
            ),

        "current_source_active":
            int(
                rule.get(
                    "expected_current_source_active"
                )
                or 0
            ),
    }


    checks = {
        "source_inactive":
            evidence[
                "source_is_active"
            ]
            is False,

        "target_active":
            evidence[
                "target_is_active"
            ]
            is True,

        "source_audit_pass":
            evidence[
                "source_audit_pass"
            ]
            is True,

        "previous_target_eligible":
            previous_target_eligible
            == expected[
                "previous_target_active"
            ],

        "previous_source_eligible":
            previous_source_eligible
            == expected[
                "previous_source_active"
            ],

        "current_target_active":
            evidence[
                "current_target_active"
            ]
            == expected[
                "current_target_active"
            ],

        "current_source_active":
            evidence[
                "current_source_active"
            ]
            == expected[
                "current_source_active"
            ],

        "rollover_sum":
            evidence[
                "current_target_active"
            ]
            == (
                previous_target_eligible
                + previous_source_eligible
            ),
    }


    return {
        "pass":
            all(
                checks.values()
            ),

        "operation_id":
            operation_id,

        "rule":
            rule,

        "evidence":
            evidence,

        "checks":
            checks,

        "reason": (
            "Nguồn đã khóa và số đội ngũ năm hiện hành "
            "tại đích khớp đúng tổng nguồn+đích năm trước."
            if all(
                checks.values()
            )
            else
            "Dấu vết dữ liệu chưa đủ để coi là đã hoàn tất trước."
        ),
    }
'''


# ============================================================
# 8. TẠO PATCH THEO AST
# ============================================================

lines = original.splitlines(
    keepends=True
)


def node_text(node) -> str:
    return "".join(
        lines[
            node.lineno - 1:
            node.end_lineno
        ]
    )


mn_original = node_text(
    mn_path_node
).rstrip(
    "\r\n"
)


mn_new = (
    mn_original
    + "\n"
    + (
        'THCS_RESOLUTION_PATH = '
        'PROJECT_DIR / "data" / '
        '"school_merger_registry" / '
        '"qd3805_thcs_resolution.json"'
    )
    + "\n"
)


edits = [
    (
        precompleted_node.lineno - 1,
        precompleted_node.end_lineno,
        NEW_PRECOMPLETED.rstrip()
        + "\n\n",
    ),

    (
        resolution_node.lineno - 1,
        resolution_node.end_lineno,
        NEW_RESOLUTION_CONTEXT.rstrip()
        + "\n\n",
    ),

    (
        mn_path_node.lineno - 1,
        mn_path_node.end_lineno,
        mn_new,
    ),
]


# Quan trọng: sửa từ dưới lên để line number AST không lệch.
for start, end, replacement in sorted(
    edits,
    key=lambda x: x[0],
    reverse=True,
):

    lines[
        start:end
    ] = [
        replacement
    ]


patched = "".join(
    lines
)


# ============================================================
# 9. KIỂM TRA SOURCE MỚI TRƯỚC KHI GHI
# ============================================================

print()
print("=" * 138)
print("6. STATIC VALIDATION")
print("=" * 138)


# Parse AST.
new_tree = ast.parse(
    patched,
    filename=str(SERVICE),
)


# Compile trong RAM.
compile(
    patched,
    str(SERVICE),
    "exec",
)


# Phải có đúng các thành phần mới.
if patched.count(
    "THCS_RESOLUTION_PATH"
) < 2:

    raise RuntimeError(
        "THCS_RESOLUTION_PATH patch FAIL."
    )


if (
    'elif level == "THCS":'
    not in patched
):

    raise RuntimeError(
        "_resolution_context THCS patch FAIL."
    )


if (
    'evidence_mode == "HISTORY_CLOSED_STATE"'
    not in patched
):

    raise RuntimeError(
        "HISTORY_CLOSED_STATE patch FAIL."
    )


# Hàm vẫn phải duy nhất.
find_function(
    new_tree,
    "_resolution_context",
)

find_function(
    new_tree,
    "_precompleted_resolution_status",
)


print(
    "AST PARSE  = PASS"
)

print(
    "COMPILE    = PASS"
)

print(
    "PATCH TYPE = WHOLE FUNCTION REPLACEMENT"
)


# ============================================================
# 10. BACKUP
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP_DIR = (
    ROOT
    / "backups"
    / (
        "backup_truoc_resolution_THCS_V3_"
        + stamp
    )
)

BACKUP_DIR.mkdir(
    parents=True,
    exist_ok=False,
)


SERVICE_BACKUP = (
    BACKUP_DIR
    / "school_merger_level_batch_service.py"
)


shutil.copy2(
    SERVICE,
    SERVICE_BACKUP,
)


NEW_SERVICE_COPY = (
    BACKUP_DIR
    / "school_merger_level_batch_service_NEW.py"
)


NEW_SERVICE_COPY.write_text(
    patched,
    encoding="utf-8",
)


NEW_RESOLUTION_COPY = (
    BACKUP_DIR
    / "qd3805_thcs_resolution_NEW.json"
)


NEW_RESOLUTION_COPY.write_text(
    json.dumps(
        resolution_payload,
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)


# Validate JSON copy.
test_resolution = json.loads(
    NEW_RESOLUTION_COPY.read_text(
        encoding="utf-8"
    )
)


if (
    test_resolution.get(
        "level_code"
    )
    != "THCS"
):

    raise RuntimeError(
        "Resolution JSON FAIL."
    )


print()
print("=" * 138)
print("7. BACKUP")
print("=" * 138)

print(
    "BACKUP DIR =",
    BACKUP_DIR,
)


# ============================================================
# 11. COMMIT SERVICE + RESOLUTION
# ============================================================

try:

    SERVICE.write_text(
        patched,
        encoding="utf-8",
    )


    RESOLUTION.write_text(
        json.dumps(
            resolution_payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


    # ========================================================
    # 12. FRESH PROCESS
    # ========================================================

    check_code = r'''
import json

from app.services import (
    school_merger_level_batch_service
    as svc
)


ctx = svc._registry_level_context(
    "THCS"
)


rows, counts, candidates, meta = (
    svc._state_rows(
        2,
        "THCS",
    )
)


preview = (
    svc.build_level_batch_preview(
        school_year_id=2,
        level_code="THCS",
    )
)


wanted = {
    "QD3805-OP-0342",
    "QD3805-OP-0343",
}


pre = []


for row in rows:

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    if op not in wanted:
        continue


    obj = (
        row.get(
            "qd3805_precompleted"
        )
        or {}
    )


    pre.append({
        "operation_id":
            op,

        "plan_id":
            row.get("id"),

        "state":
            row.get(
                "batch_state"
            ),

        "label":
            row.get(
                "batch_label"
            ),

        "precompleted_pass":
            obj.get(
                "pass"
            ),

        "checks":
            obj.get(
                "checks"
            ),

        "evidence":
            obj.get(
                "evidence"
            ),
    })


result = {
    "registry_summary":
        svc.registry_level_summary(
            "THCS"
        ),

    "counts":
        counts,

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

    "registry_unresolved_count":
        preview.get(
            "registry_unresolved_count"
        ),

    "registry_deferred_unresolved_count":
        preview.get(
            "registry_deferred_unresolved_count"
        ),

    "precompleted":
        pre,

    "special_orphans":
        ctx.get(
            "special_orphans"
        )
        or [],
}


print(
    "JSON_RESULT="
    + json.dumps(
        result,
        ensure_ascii=False,
        default=str,
    )
)
'''


    env = dict(
        os.environ
    )

    env[
        "PYTHONDONTWRITEBYTECODE"
    ] = "1"


    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            check_code,
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


    print()
    print("=" * 138)
    print("8. VALIDATE SAU CAI")
    print("=" * 138)


    print(
        proc.stdout
    )


    if proc.stderr.strip():

        print(
            "STDERR:"
        )

        print(
            proc.stderr
        )


    if proc.returncode != 0:

        raise RuntimeError(
            "Fresh-process validation FAIL."
        )


    json_text = None


    for line in (
        proc.stdout.splitlines()
    ):

        if line.startswith(
            "JSON_RESULT="
        ):

            json_text = line[
                len(
                    "JSON_RESULT="
                ):
            ]

            break


    if not json_text:

        raise RuntimeError(
            "Khong co JSON_RESULT."
        )


    result = json.loads(
        json_text
    )


    pre_map = {
        str(
            x.get(
                "operation_id"
            )
            or ""
        ):
        x

        for x in (
            result.get(
                "precompleted"
            )
            or []
        )
    }


    for op in (
        "QD3805-OP-0342",
        "QD3805-OP-0343",
    ):

        item = (
            pre_map.get(op)
            or {}
        )

        if (
            item.get("state")
            != "DONE"
        ):

            raise RuntimeError(
                op
                + " CHUA VE DONE."
            )


        if (
            item.get(
                "precompleted_pass"
            )
            is not True
        ):

            raise RuntimeError(
                op
                + " PRECOMPLETED CHUA PASS."
            )


    special_orphans = (
        result.get(
            "special_orphans"
        )
        or []
    )


    nghi_huong_ok = any(
        isinstance(
            x,
            dict,
        )
        and int(
            x.get("stt")
            or 0
        ) == 110
        and str(
            x.get(
                "school"
            )
            or ""
        )
        == "THCS Nghi Hương"
        and str(
            x.get(
                "status"
            )
            or ""
        ).startswith(
            "GIỮ NGUYÊN"
        )
        for x in special_orphans
    )


    if not nghi_huong_ok:

        raise RuntimeError(
            "THCS Nghi Huong chua duoc "
            "nhan GIU NGUYEN."
        )


    # Trạng thái mong đợi sau đúng 3 điều chỉnh này.
    counts = (
        result.get(
            "counts"
        )
        or {}
    )


    print()
    print(
        "COUNTS AFTER =",
        counts,
    )

    print(
        "CANDIDATE    =",
        result.get(
            "candidate_count"
        ),
    )

    print(
        "BLOCK EFFECT =",
        result.get(
            "effective_block_count"
        ),
    )

    print(
        "DEFERRED     =",
        result.get(
            "registry_deferred_unresolved_count"
        ),
    )


    if int(
        counts.get(
            "DONE"
        )
        or 0
    ) != 84:

        raise RuntimeError(
            "DUNG: DONE khong bang 84."
        )


    if int(
        counts.get(
            "READY"
        )
        or 0
    ) != 13:

        raise RuntimeError(
            "DUNG: READY khong bang 13."
        )


    if int(
        counts.get(
            "BLOCK"
        )
        or 0
    ) != 19:

        raise RuntimeError(
            "DUNG: BLOCK khong bang 19."
        )


    if int(
        result.get(
            "candidate_count"
        )
        or 0
    ) != 13:

        raise RuntimeError(
            "DUNG: candidate_count khong bang 13."
        )


    if int(
        result.get(
            "registry_deferred_unresolved_count"
        )
        or 0
    ) != 1:

        raise RuntimeError(
            "DUNG: Nghi Huong chua duoc "
            "loai khoi blocker."
        )


    # ========================================================
    # 13. FILE SAFETY
    # ========================================================

    db_after = sha256(
        DB
    )

    lock_after = sha256(
        LOCK
    )

    roster_after = sha256(
        ROSTER
    )

    history_after = sha256(
        HISTORY
    )


    print()
    print("=" * 138)
    print("9. FILE SAFETY")
    print("=" * 138)


    print(
        "DB      :",
        before["db"],
        "->",
        db_after,
    )

    print(
        "LOCK    :",
        before["lock"],
        "->",
        lock_after,
    )

    print(
        "ROSTER  :",
        before["roster"],
        "->",
        roster_after,
    )

    print(
        "HISTORY :",
        before["history"],
        "->",
        history_after,
    )

    print(
        "SERVICE NEW SHA =",
        sha256(SERVICE),
    )

    print(
        "RESOLUTION SHA  =",
        sha256(RESOLUTION),
    )


    if db_after != before["db"]:
        raise RuntimeError(
            "DATABASE BI THAY DOI."
        )


    if lock_after != before["lock"]:
        raise RuntimeError(
            "LEVEL LOCK BI THAY DOI."
        )


    if roster_after != before["roster"]:
        raise RuntimeError(
            "ROSTER BI THAY DOI."
        )


    if history_after != before["history"]:
        raise RuntimeError(
            "HISTORY BI THAY DOI."
        )


except Exception:

    print()
    print("=" * 138)
    print("LOI - TU KHOI PHUC V3")
    print("=" * 138)


    shutil.copy2(
        SERVICE_BACKUP,
        SERVICE,
    )


    if RESOLUTION.exists():
        RESOLUTION.unlink()


    print(
        "SERVICE RESTORED SHA =",
        sha256(SERVICE),
    )

    print(
        "RESOLUTION THCS = KHONG GIU LAI"
    )

    print(
        "DATABASE = KHONG TAC DONG"
    )

    raise


print()
print("=" * 138)
print("CAI RESOLUTION THCS BUOC 1 V3: THANH CONG")
print("=" * 138)

print(
    "THCS NGHI HUONG : GIU NGUYEN"
)

print(
    "OP-0342         : DONE - KHONG CHAY LAI"
)

print(
    "OP-0343         : DONE - KHONG CHAY LAI"
)

print(
    "DONE            : 84"
)

print(
    "READY           : 13"
)

print(
    "BLOCK           : 19"
)

print(
    "DATABASE        : KHONG THAY DOI"
)

print(
    "SAP NHAP THCS   : CHUA CHAY"
)

print("=" * 138)
