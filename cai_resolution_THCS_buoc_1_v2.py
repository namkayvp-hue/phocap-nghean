from __future__ import annotations

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


EXPECTED_DB = (
    "882e4925fd3e39d7e097ce127612c093"
    "852075e608d3f937294135282afec75a"
)

EXPECTED_SERVICE = (
    "963b8d6a280d8abef8e96486abd87d77"
    "cea289b08d2edb497647f250ed1b2af8"
)

EXPECTED_LOCK = (
    "ad310048a4c5b239404e0902cc04fda1"
    "d73474d11a739a2ca009d2727e4390c3"
)

EXPECTED_ROSTER = (
    "926528e0ae600a6b950b459c6f8ec5c"
    "6810e69d49158d1ff3c9a3d76c0bca657"
)


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
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")

    return con


print("=" * 136)
print("CAI RESOLUTION THCS - BUOC 1 V2")
print("NGHI HUONG GIU NGUYEN + 2 NGHI LOC PRECOMPLETED")
print("=" * 136)

print("KHONG GHI DATABASE.")
print("KHONG CHAY SAP NHAP THCS.")


# ============================================================
# 1. SERVER / WAL
# ============================================================

print()
print("=" * 136)
print("1. SERVER / WAL GATE")
print("=" * 136)

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
            "DUNG: server/Uvicorn chua dung hoan toan."
        )


# ============================================================
# 2. HASH
# ============================================================

print()
print("=" * 136)
print("2. HASH GATE")
print("=" * 136)

before = {
    "db": sha256(DB),
    "service": sha256(SERVICE),
    "lock": sha256(LOCK),
    "roster": sha256(ROSTER),
    "history": sha256(HISTORY),
}

for key, value in before.items():
    print(
        f"{key:12s} = {value}"
    )


if before["db"] != EXPECTED_DB:
    raise RuntimeError(
        "DUNG: database khong dung snapshot da khoa."
    )

if before["service"] != EXPECTED_SERVICE:
    raise RuntimeError(
        "DUNG: service da thay doi. "
        "Khong duoc tiep tuc tu dong."
    )

if before["lock"] != EXPECTED_LOCK:
    raise RuntimeError(
        "DUNG: level lock da thay doi."
    )

if before["roster"] != EXPECTED_ROSTER:
    raise RuntimeError(
        "DUNG: THCS roster da thay doi."
    )


if RESOLUTION.exists():

    print(
        "THCS RESOLUTION DA TON TAI:",
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
# 3. DB HEALTH + NGHI HUONG
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
    print("=" * 136)
    print("3. DATABASE HEALTH")
    print("=" * 136)

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
        WHERE id=1408
          AND TRIM(code)='40413505'
        """
    ).fetchone()


    print()
    print("=" * 136)
    print("4. THCS NGHI HUONG")
    print("=" * 136)

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
# 5. LICH SU NGHI LOC
# ============================================================

history_payload = json.loads(
    HISTORY.read_text(
        encoding="utf-8-sig"
    )
)

history_plans = [
    dict(x)
    for x in (
        history_payload.get("plans")
        or []
    )
    if isinstance(x, dict)
]


EXPECTED_HISTORY = {
    "QD3805-NGHI-LOC-THCS-NGHI-DIEN": {
        "source": 1608,
        "target": 1605,
    },

    "QD3805-NGHI-LOC-THCS-NGHI-TRUNG": {
        "source": 1607,
        "target": 1606,
    },
}


print()
print("=" * 136)
print("5. LICH SU NGHI LOC")
print("=" * 136)


for plan_id, expected in EXPECTED_HISTORY.items():

    matches = [
        x
        for x in history_plans
        if str(
            x.get("id")
            or ""
        ) == plan_id
    ]

    if len(matches) != 1:
        raise RuntimeError(
            "DUNG: history plan khong duy nhat: "
            + plan_id
        )

    plan = matches[0]

    sources = sorted(
        int(x)
        for x in (
            plan.get(
                "source_school_ids"
            )
            or []
        )
    )

    target = int(
        plan.get(
            "target_school_id"
        )
        or 0
    )

    status = str(
        plan.get(
            "status"
        )
        or ""
    ).upper()


    print(
        plan_id,
        "|",
        status,
        "| sources=",
        sources,
        "| target=",
        target,
    )


    if status != "COMPLETED":
        raise RuntimeError(
            "DUNG: history khong COMPLETED."
        )

    if sources != [
        expected["source"]
    ]:
        raise RuntimeError(
            "DUNG: source history sai."
        )

    if target != expected["target"]:
        raise RuntimeError(
            "DUNG: target history sai."
        )


# ============================================================
# 6. BACKUP SERVICE
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP_DIR = (
    ROOT
    / "backups"
    / (
        "backup_truoc_resolution_THCS_V2_"
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


print()
print("=" * 136)
print("6. BACKUP")
print("=" * 136)

print(
    "BACKUP DIR =",
    BACKUP_DIR,
)

print(
    "SERVICE    =",
    SERVICE_BACKUP,
)


# ============================================================
# 7. RESOLUTION PAYLOAD
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
            "Phương án đã hoàn tất trước phải được nhận DONE "
            "và tuyệt đối không chạy lại."
        ),
        (
            "THCS Nghi Hương mã 40413505 được xác nhận "
            "GIỮ NGUYÊN do dòng QĐ3805 thiếu chữ Giữ nguyên."
        ),
        (
            "Các nghiệp vụ tách điểm, tiếp nhận điểm, "
            "liên cấp hoặc chưa đủ nguồn-đích "
            "không được ép vào batch THCS thuần."
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
                    "Đã hoàn tất trước theo lịch sử QĐ3805. "
                    "Nguồn inactive, đích active, "
                    "không còn CURRENT/FUTURE tại nguồn "
                    "và không còn tài khoản active tại nguồn. "
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
                    "Đã hoàn tất trước theo lịch sử QĐ3805. "
                    "Nguồn inactive, đích active, "
                    "không còn CURRENT/FUTURE tại nguồn "
                    "và không còn tài khoản active tại nguồn. "
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
                    "Đã xác nhận dòng QĐ3805 bị thiếu "
                    "chữ 'Giữ nguyên'. "
                    "Giữ nguyên school_id=1408, "
                    "mã 40413505 và toàn bộ dữ liệu."
                ),
        }
    ],
}


# ============================================================
# 8. PATCH SERVICE ROBUST
# ============================================================

original = SERVICE.read_text(
    encoding="utf-8"
)

patched = original


def function_bounds(
    text: str,
    function_name: str,
):

    marker = (
        "def "
        + function_name
        + "("
    )

    start = text.find(
        marker
    )

    if start < 0:
        raise RuntimeError(
            "Khong tim thay ham "
            + function_name
        )

    next_def = text.find(
        "\ndef ",
        start + len(marker),
    )

    if next_def < 0:
        next_def = len(text)

    return start, next_def


try:

    # --------------------------------------------------------
    # 8A. THCS_RESOLUTION_PATH
    # --------------------------------------------------------

    print()
    print("=" * 136)
    print("7. PATCH SERVICE")
    print("=" * 136)


    if (
        "THCS_RESOLUTION_PATH"
        in patched
    ):
        raise RuntimeError(
            "Service da co THCS_RESOLUTION_PATH bat ngo."
        )


    mn_constant = (
        'MN_RESOLUTION_PATH = PROJECT_DIR / "data" '
        '/ "school_merger_registry" '
        '/ "qd3805_mn_resolution.json"'
    )


    pos = patched.find(
        mn_constant
    )

    if pos < 0:
        raise RuntimeError(
            "Khong tim thay MN_RESOLUTION_PATH."
        )


    insert_pos = (
        pos
        + len(
            mn_constant
        )
    )


    patched = (
        patched[:insert_pos]
        + '\n'
        + (
            'THCS_RESOLUTION_PATH = PROJECT_DIR / "data" '
            '/ "school_merger_registry" '
            '/ "qd3805_thcs_resolution.json"'
        )
        + patched[insert_pos:]
    )


    print(
        "PATCH A = PASS"
    )


    # --------------------------------------------------------
    # 8B. _resolution_context
    # --------------------------------------------------------

    start, end = function_bounds(
        patched,
        "_resolution_context",
    )

    segment = patched[
        start:end
    ]


    if (
        'elif level == "THCS":'
        in segment
    ):
        raise RuntimeError(
            "_resolution_context da co THCS bat ngo."
        )


    else_marker = (
        '    else:\n'
        '        payload, fingerprint = {}, ""'
    )


    rel = segment.find(
        else_marker
    )

    if rel < 0:
        raise RuntimeError(
            "Khong tim thay else cua "
            "_resolution_context."
        )


    absolute = start + rel


    thcs_branch = '''    elif level == "THCS":
        payload, fingerprint = _load_resolution_file(
            THCS_RESOLUTION_PATH,
            "THCS",
        )
'''


    patched = (
        patched[:absolute]
        + thcs_branch
        + patched[absolute:]
    )


    print(
        "PATCH B = PASS"
    )


    # --------------------------------------------------------
    # 8C. THÊM HELPER HISTORY_CLOSED_STATE
    # --------------------------------------------------------

    helper_marker = (
        "def _precompleted_resolution_status("
    )


    helper_pos = patched.find(
        helper_marker
    )

    if helper_pos < 0:
        raise RuntimeError(
            "Khong tim thay "
            "_precompleted_resolution_status."
        )


    helper_code = r'''
def _precompleted_history_closed_status(
    *,
    operation_id: str,
    rule: dict[str, Any],
) -> dict[str, Any]:
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

        if source is None or target is None:
            return {
                "pass": False,
                "operation_id": operation_id,
                "rule": rule,
                "reason": (
                    "Không tìm thấy đủ trường "
                    "nguồn/đích của phương án "
                    "đã hoàn tất trước."
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
            SELECT id
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
                "Không đọc được lịch sử: "
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
            ) is False,

        "target_active":
            bool(
                target["is_active"]
            ) is True,

        "current_future_residual_zero":
            not bool(residual),

        "active_source_users_zero":
            active_source_users == 0,
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
            "HISTORY_CLOSED_STATE",

        "checks":
            checks,

        "evidence": {
            "source_school_id":
                source_id,

            "target_school_id":
                target_id,

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

        "reason": (
            "Lịch sử COMPLETED và trạng thái "
            "DB đều xác nhận đã hoàn tất trước; "
            "không chạy lại."
            if passed
            else
            "Dấu vết lịch sử hoặc trạng thái DB "
            "chưa đủ để coi là đã hoàn tất trước."
        ),
    }


'''


    patched = (
        patched[:helper_pos]
        + helper_code
        + patched[helper_pos:]
    )


    print(
        "PATCH C = PASS"
    )


    # --------------------------------------------------------
    # 8D. GỌI HELPER TỪ _precompleted_resolution_status
    # --------------------------------------------------------

    start, end = function_bounds(
        patched,
        "_precompleted_resolution_status",
    )

    segment = patched[
        start:end
    ]


    source_line = (
        '    source_code = '
        'str(rule.get("source_school_code") or "").strip()'
    )


    rel = segment.find(
        source_line
    )

    if rel < 0:

        # fallback chỉ tìm đầu dòng source_code,
        # không phụ thuộc toàn bộ biểu thức.
        rel = segment.find(
            "    source_code ="
        )


    if rel < 0:
        raise RuntimeError(
            "Khong tim thay dong source_code "
            "ben trong _precompleted_resolution_status."
        )


    absolute = start + rel


    dispatch_code = '''    evidence_mode = str(
        rule.get("evidence_mode") or ""
    ).strip().upper()

    if evidence_mode == "HISTORY_CLOSED_STATE":
        return _precompleted_history_closed_status(
            operation_id=operation_id,
            rule=rule,
        )

'''


    patched = (
        patched[:absolute]
        + dispatch_code
        + patched[absolute:]
    )


    print(
        "PATCH D = PASS"
    )


    # ========================================================
    # 9. TEMP + COMPILE
    # ========================================================

    SERVICE_TMP = (
        BACKUP_DIR
        / "school_merger_level_batch_service_NEW.py"
    )

    RESOLUTION_TMP = (
        BACKUP_DIR
        / "qd3805_thcs_resolution_NEW.json"
    )


    SERVICE_TMP.write_text(
        patched,
        encoding="utf-8",
    )


    py_compile.compile(
        str(SERVICE_TMP),
        doraise=True,
    )


    RESOLUTION_TMP.write_text(
        json.dumps(
            resolution_payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


    check_json = json.loads(
        RESOLUTION_TMP.read_text(
            encoding="utf-8"
        )
    )


    if (
        check_json.get("level_code")
        != "THCS"
    ):
        raise RuntimeError(
            "Resolution level FAIL."
        )


    if len(
        check_json.get(
            "precompleted"
        )
        or []
    ) != 2:
        raise RuntimeError(
            "Precompleted count FAIL."
        )


    deferred = (
        check_json.get(
            "deferred_orphans"
        )
        or []
    )


    if (
        len(deferred) != 1
        or int(
            deferred[0].get("stt")
            or 0
        ) != 110
        or str(
            deferred[0].get(
                "school_code"
            )
            or ""
        ) != "40413505"
    ):
        raise RuntimeError(
            "Nghi Huong resolution FAIL."
        )


    print(
        "COMPILE / JSON CHECK = PASS"
    )


    # ========================================================
    # 10. COMMIT 2 FILE
    # ========================================================

    shutil.copy2(
        SERVICE_TMP,
        SERVICE,
    )

    shutil.copy2(
        RESOLUTION_TMP,
        RESOLUTION,
    )


    # ========================================================
    # 11. FRESH PROCESS VALIDATE
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

        "precompleted":
            row.get(
                "qd3805_precompleted"
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
    print("=" * 136)
    print("8. VALIDATE SAU CAI")
    print("=" * 136)


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
            "Fresh process validation FAIL."
        )


    json_line = None

    for line in (
        proc.stdout.splitlines()
    ):
        if line.startswith(
            "JSON_RESULT="
        ):
            json_line = line[
                len(
                    "JSON_RESULT="
                ):
            ]
            break


    if not json_line:
        raise RuntimeError(
            "Khong doc duoc JSON_RESULT."
        )


    parsed = json.loads(
        json_line
    )


    states = {
        str(
            x.get(
                "operation_id"
            )
            or ""
        ):
        str(
            x.get(
                "state"
            )
            or ""
        )

        for x in (
            parsed.get(
                "precompleted"
            )
            or []
        )
    }


    if (
        states.get(
            "QD3805-OP-0342"
        ) != "DONE"
    ):
        raise RuntimeError(
            "OP-0342 chua DONE."
        )


    if (
        states.get(
            "QD3805-OP-0343"
        ) != "DONE"
    ):
        raise RuntimeError(
            "OP-0343 chua DONE."
        )


    if int(
        parsed.get(
            "registry_deferred_unresolved_count"
        )
        or 0
    ) != 1:
        raise RuntimeError(
            "Nghi Huong chua duoc "
            "xac nhan khong chan batch."
        )


    special_orphans = (
        parsed.get(
            "special_orphans"
        )
        or []
    )


    nghi_huong_ok = any(
        int(
            x.get("stt")
            or 0
        ) == 110

        and str(
            x.get(
                "status"
            )
            or ""
        ).startswith(
            "GIỮ NGUYÊN"
        )

        for x in special_orphans
        if isinstance(
            x,
            dict,
        )
    )


    if not nghi_huong_ok:
        raise RuntimeError(
            "THCS Nghi Huong chua hien "
            "trang thai GIU NGUYEN."
        )


    # ========================================================
    # 12. SAFETY
    # ========================================================

    db_after = sha256(DB)
    lock_after = sha256(LOCK)
    roster_after = sha256(ROSTER)


    print()
    print("=" * 136)
    print("9. FILE SAFETY")
    print("=" * 136)


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
        "SERVICE NEW SHA =",
        sha256(SERVICE),
    )

    print(
        "RESOLUTION SHA  =",
        sha256(RESOLUTION),
    )

    print(
        "BACKUP DIR      =",
        BACKUP_DIR,
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
            "THCS ROSTER BI THAY DOI."
        )


except Exception:

    print()
    print("=" * 136)
    print("LOI - TU KHOI PHUC")
    print("=" * 136)


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
print("=" * 136)
print("CAI RESOLUTION THCS BUOC 1 V2: THANH CONG")
print("=" * 136)

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
    "DATABASE        : KHONG THAY DOI"
)

print(
    "SAP NHAP THCS   : CHUA CHAY"
)

print("=" * 136)
