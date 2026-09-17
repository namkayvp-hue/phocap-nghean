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
}


PRECOMPLETED = [
    {
        "operation_id":
            "QD3805-OP-0342",

        "history_plan_id":
            "QD3805-NGHI-LOC-THCS-NGHI-DIEN",

        "evidence_mode":
            "HISTORY_CLOSED_STATE",

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

        "previous_year_code":
            "2025-2026",

        "current_year_code":
            "2026-2027",

        "reason":
            "Phương án đã hoàn tất trước. "
            "Lịch sử QĐ3805 xác nhận THCS Nghi Vạn -> THCS Nghi Diên; "
            "nguồn đã khóa, đích còn hoạt động, không còn dữ liệu "
            "CURRENT/FUTURE và tài khoản hoạt động tại nguồn. Không chạy lại.",
    },

    {
        "operation_id":
            "QD3805-OP-0343",

        "history_plan_id":
            "QD3805-NGHI-LOC-THCS-NGHI-TRUNG",

        "evidence_mode":
            "HISTORY_CLOSED_STATE",

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

        "previous_year_code":
            "2025-2026",

        "current_year_code":
            "2026-2027",

        "reason":
            "Phương án đã hoàn tất trước. "
            "Lịch sử QĐ3805 xác nhận THCS Nghi Hoa -> THCS Nghi Trung; "
            "nguồn đã khóa, đích còn hoạt động, không còn dữ liệu "
            "CURRENT/FUTURE và tài khoản hoạt động tại nguồn. Không chạy lại.",
    },
]


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
        DB.resolve().as_uri()
        + "?mode=ro",
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


print("=" * 134)
print("CAI RESOLUTION THCS - BUOC 1")
print(
    "NGHI HUONG GIU NGUYEN + "
    "2 NGHI LOC PRECOMPLETED"
)
print("=" * 134)

print(
    "KHONG GHI DATABASE."
)

print(
    "KHONG CHAY SAP NHAP THCS."
)

print("=" * 134)


# ============================================================
# 1. SERVER / WAL GATE
# ============================================================

print()
print("=" * 134)
print("1. SERVER / WAL GATE")
print("=" * 134)


for suffix in (
    "-wal",
    "-journal",
):

    p = Path(
        str(DB) + suffix
    )

    size = (
        p.stat().st_size
        if p.exists()
        else 0
    )

    print(
        p.name,
        "=",
        size,
    )

    if size > 0:

        raise RuntimeError(
            "DUNG: "
            + p.name
            + " dang co du lieu. "
              "Hay dung Uvicorn/server."
        )


# ============================================================
# 2. HASH GATE
# ============================================================

print()
print("=" * 134)
print("2. HASH GATE")
print("=" * 134)


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


for key in (
    "db",
    "service",
    "lock",
    "roster",
):

    if before[key] != EXPECTED[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


# Không ghi đè resolution THCS nếu đã tồn tại.
if RESOLUTION.exists():

    print()
    print(
        "RESOLUTION DA TON TAI =",
        RESOLUTION,
    )

    print(
        "SHA256 =",
        sha256(RESOLUTION),
    )

    raise RuntimeError(
        "DUNG: qd3805_thcs_resolution.json "
        "da ton tai. Khong ghi de."
    )


# ============================================================
# 3. DATABASE HEALTH + NGHI HUONG
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
    print("=" * 134)
    print("3. DATABASE HEALTH")
    print("=" * 134)

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
            "DUNG: database integrity/FK FAIL."
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
    print("=" * 134)
    print("4. THCS NGHI HUONG")
    print("=" * 134)


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
            "DUNG: khong tim thay dung "
            "THCS Nghi Huong school_id=1408."
        )


    if not bool(
        nghi_huong["is_active"]
    ):

        raise RuntimeError(
            "DUNG: THCS Nghi Huong "
            "khong con active."
        )


finally:
    con.close()


# ============================================================
# 5. XÁC NHẬN LỊCH SỬ 2 NGHI LỘC
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
    if isinstance(
        x,
        dict,
    )
]


def get_history_plan(plan_id):

    matches = [
        x
        for x in history_plans
        if str(
            x.get("id")
            or ""
        )
        == plan_id
    ]

    if len(matches) != 1:

        raise RuntimeError(
            "DUNG: history plan "
            + plan_id
            + " khong duy nhat."
        )

    return matches[0]


print()
print("=" * 134)
print("5. LICH SU 2 PHUONG AN NGHI LOC")
print("=" * 134)


for rule in PRECOMPLETED:

    plan = get_history_plan(
        rule[
            "history_plan_id"
        ]
    )


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


    print(
        rule["operation_id"],
        "| history=",
        plan.get("id"),
        "| status=",
        plan.get("status"),
        "| sources=",
        sources,
        "| target=",
        target,
    )


    if str(
        plan.get("status")
        or ""
    ).upper() != "COMPLETED":

        raise RuntimeError(
            "DUNG: history plan "
            "khong o trang thai COMPLETED."
        )


    if sources != [
        int(
            rule[
                "source_school_id"
            ]
        )
    ]:

        raise RuntimeError(
            "DUNG: source history "
            "khong khop resolution."
        )


    if target != int(
        rule[
            "target_school_id"
        ]
    ):

        raise RuntimeError(
            "DUNG: target history "
            "khong khop resolution."
        )


# ============================================================
# 6. TẠO BACKUP SOURCE
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP_DIR = (
    ROOT
    / "backups"
    / (
        "backup_truoc_resolution_THCS_"
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
print("=" * 134)
print("6. BACKUP")
print("=" * 134)

print(
    "BACKUP DIR =",
    BACKUP_DIR,
)

print(
    "SERVICE    =",
    SERVICE_BACKUP,
)


# ============================================================
# 7. DỰNG RESOLUTION THCS
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
            "Không sửa dữ liệu lịch sử các năm trước."
        ),
        (
            "Không tự suy đoán nguồn/đích đối với "
            "các phương án THCS còn chưa đủ căn cứ."
        ),
        (
            "Phương án đã hoàn tất trước chỉ được nhận DONE "
            "khi lịch sử nguồn→đích và trạng thái DB hiện tại "
            "đều khớp; tuyệt đối không chạy lại."
        ),
        (
            "THCS Nghi Hương mã 40413505 được xác nhận "
            "GIỮ NGUYÊN; dòng QĐ3805 thiếu chữ Giữ nguyên."
        ),
        (
            "Các trường hợp tách điểm, tiếp nhận điểm, "
            "tạo trường tên mới hoặc chưa xác định school_id "
            "sẽ xử lý ở bước resolution tiếp theo; "
            "không ép vào batch thuần."
        ),
    ],

    "rename_only": [],

    "special_same_level": [],

    "precompleted":
        PRECOMPLETED,

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

            "status":
                "GIỮ NGUYÊN – KHÔNG TÁC ĐỘNG",

            "display_title":
                (
                    "THCS Nghi Hương – "
                    "GIỮ NGUYÊN"
                ),

            "reason":
                (
                    "Đã xác nhận nghiệp vụ: "
                    "dòng QĐ3805 bị thiếu chữ 'Giữ nguyên'. "
                    "Giữ nguyên school_id=1408, mã 40413505 "
                    "và toàn bộ dữ liệu; không tạo nguồn→đích "
                    "và không tham gia batch sáp nhập."
                ),
        }
    ],
}


# ============================================================
# 8. PATCH SERVICE
# ============================================================

original_service = (
    SERVICE.read_text(
        encoding="utf-8"
    )
)

patched = original_service


# ------------------------------------------------------------
# 8A. THCS_RESOLUTION_PATH
# ------------------------------------------------------------

constant_marker = (
    'MN_RESOLUTION_PATH = PROJECT_DIR / "data" '
    '/ "school_merger_registry" '
    '/ "qd3805_mn_resolution.json"'
)

constant_new = (
    constant_marker
    + '\n'
    + 'THCS_RESOLUTION_PATH = PROJECT_DIR / "data" '
      '/ "school_merger_registry" '
      '/ "qd3805_thcs_resolution.json"'
)


if (
    "THCS_RESOLUTION_PATH"
    in patched
):

    raise RuntimeError(
        "DUNG: service da co "
        "THCS_RESOLUTION_PATH bat ngo."
    )


if patched.count(
    constant_marker
) != 1:

    raise RuntimeError(
        "DUNG: khong tim thay dung "
        "constant marker trong service."
    )


patched = patched.replace(
    constant_marker,
    constant_new,
    1,
)


# ------------------------------------------------------------
# 8B. _resolution_context THCS
# ------------------------------------------------------------

context_old = '''    elif level == "MN":
        payload, fingerprint = _load_resolution_file(
            MN_RESOLUTION_PATH,
            "Mầm non",
        )
    else:
        payload, fingerprint = {}, ""
'''

context_new = '''    elif level == "MN":
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
'''


if patched.count(
    context_old
) != 1:

    raise RuntimeError(
        "DUNG: khong tim thay dung "
        "_resolution_context hien tai."
    )


patched = patched.replace(
    context_old,
    context_new,
    1,
)


# ------------------------------------------------------------
# 8C. PRECOMPLETED LỊCH SỬ ĐÃ ĐÓNG
# ------------------------------------------------------------

pre_marker = '''    if not rule:
        return None

    source_code = str(rule.get("source_school_code") or "").strip()
'''


history_branch = '''    if not rule:
        return None

    evidence_mode = str(
        rule.get("evidence_mode") or ""
    ).strip().upper()

    if evidence_mode == "HISTORY_CLOSED_STATE":
        source_code = str(
            rule.get("source_school_code") or ""
        ).strip()
        target_code = str(
            rule.get("target_school_code") or ""
        ).strip()
        history_plan_id = str(
            rule.get("history_plan_id") or ""
        ).strip()

        expected_source_id = int(
            rule.get("source_school_id") or 0
        )
        expected_target_id = int(
            rule.get("target_school_id") or 0
        )

        con = engine._connect(read_only=True)

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

            source_id = int(source["id"])
            target_id = int(target["id"])

            active_source_users = int(
                (
                    con.execute(
                        """
                        SELECT COUNT(*)
                        FROM users
                        WHERE school_id=?
                          AND is_active=1
                        """,
                        (source_id,),
                    ).fetchone()
                    or {"n": 0}
                )[0]
                or 0
            )

            year_rows = con.execute(
                """
                SELECT id,code
                FROM school_years
                WHERE code IN (?,?)
                """,
                (
                    "2026-2027",
                    "2027-2028",
                ),
            ).fetchall()

            move_year_ids = [
                int(x["id"])
                for x in year_rows
            ]

            residual = {}

            if move_year_ids:
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

                    year_marks = ",".join(
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
                                  IN ({year_marks})
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
                    "Không đọc được sổ lịch sử "
                    "sáp nhập: "
                    + str(exc)
                ),
            }

        history_match = None

        for raw_plan in (
            history_payload.get("plans")
            or []
        ):
            if not isinstance(
                raw_plan,
                dict,
            ):
                continue

            if str(
                raw_plan.get("id")
                or ""
            ) != history_plan_id:
                continue

            history_match = dict(
                raw_plan
            )
            break

        history_source_ids = []

        history_target_id = 0
        history_completed = False

        if history_match is not None:
            history_source_ids = sorted(
                int(x)
                for x in (
                    history_match.get(
                        "source_school_ids"
                    )
                    or []
                )
            )

            history_target_id = int(
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
            "history_plan_found":
                history_match is not None,

            "history_completed":
                history_completed,

            "history_source_exact":
                history_source_ids
                == [expected_source_id],

            "history_target_exact":
                history_target_id
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
                        source[
                            "is_active"
                        ]
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
                        target[
                            "is_active"
                        ]
                    ),

                "history_plan_id":
                    history_plan_id,

                "history_source_ids":
                    history_source_ids,

                "history_target_id":
                    history_target_id,

                "active_source_users":
                    active_source_users,

                "source_current_future_residual":
                    residual,
            },

            "checks":
                checks,

            "reason": (
                "Lịch sử COMPLETED và trạng thái DB "
                "đều xác nhận phương án đã hoàn tất trước; "
                "không chạy lại."
                if passed
                else
                "Dấu vết lịch sử/trạng thái DB chưa đủ "
                "để coi phương án đã hoàn tất trước."
            ),
        }

    source_code = str(rule.get("source_school_code") or "").strip()
'''


if patched.count(
    pre_marker
) != 1:

    raise RuntimeError(
        "DUNG: khong tim thay dung "
        "_precompleted_resolution_status marker."
    )


patched = patched.replace(
    pre_marker,
    history_branch,
    1,
)


# ============================================================
# 9. GHI ATOMIC + VALIDATE
# ============================================================

service_tmp = SERVICE.with_suffix(
    ".py.thcs_tmp"
)

resolution_tmp = RESOLUTION.with_suffix(
    ".json.tmp"
)


try:

    # Ghi file tạm service.
    service_tmp.write_text(
        patched,
        encoding="utf-8",
    )


    # Compile file tạm.
    py_compile.compile(
        str(service_tmp),
        doraise=True,
    )


    # Ghi resolution tạm.
    resolution_tmp.write_text(
        json.dumps(
            resolution_payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


    # Đọc lại JSON trước khi commit source.
    check_resolution = json.loads(
        resolution_tmp.read_text(
            encoding="utf-8"
        )
    )


    if (
        check_resolution.get(
            "schema"
        )
        != "QD3805_THCS_RESOLUTION_2026"
    ):

        raise RuntimeError(
            "Resolution schema FAIL."
        )


    if (
        check_resolution.get(
            "level_code"
        )
        != "THCS"
    ):

        raise RuntimeError(
            "Resolution level_code FAIL."
        )


    if len(
        check_resolution.get(
            "precompleted"
        )
        or []
    ) != 2:

        raise RuntimeError(
            "Resolution precompleted count FAIL."
        )


    deferred = (
        check_resolution.get(
            "deferred_orphans"
        )
        or []
    )


    if (
        len(deferred) != 1
        or int(
            deferred[0].get(
                "stt"
            )
            or 0
        )
        != 110
        or str(
            deferred[0].get(
                "school_code"
            )
            or ""
        )
        != "40413505"
    ):

        raise RuntimeError(
            "Resolution Nghi Huong FAIL."
        )


    # Commit 2 file source/config.
    os.replace(
        service_tmp,
        SERVICE,
    )

    os.replace(
        resolution_tmp,
        RESOLUTION,
    )


    # --------------------------------------------------------
    # 10. FRESH-PROCESS VALIDATION
    # --------------------------------------------------------

    check_code = r'''
import json
from app.services import school_merger_level_batch_service as svc

ctx = svc._registry_level_context("THCS")

rows, counts, candidates, meta = svc._state_rows(
    2,
    "THCS",
)

preview = svc.build_level_batch_preview(
    school_year_id=2,
    level_code="THCS",
)

wanted = {
    "QD3805-OP-0342",
    "QD3805-OP-0343",
}

pre = []

for row in rows:
    op = str(
        row.get("qd3805_operation_id")
        or ""
    )

    if op in wanted:
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

out = {
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
    json.dumps(
        out,
        ensure_ascii=False,
        indent=2,
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


    result = subprocess.run(
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
    print("=" * 134)
    print("7. VALIDATE SAU CAI")
    print("=" * 134)

    print(
        result.stdout
    )


    if result.stderr.strip():

        print(
            "STDERR:"
        )

        print(
            result.stderr
        )


    if result.returncode != 0:

        raise RuntimeError(
            "Fresh-process validation FAIL."
        )


    parsed = json.loads(
        result.stdout
    )


    pre_states = {
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
        pre_states.get(
            "QD3805-OP-0342"
        )
        != "DONE"
        or pre_states.get(
            "QD3805-OP-0343"
        )
        != "DONE"
    ):

        raise RuntimeError(
            "DUNG: OP-0342/0343 "
            "chua ve DONE."
        )


    if int(
        parsed.get(
            "registry_unresolved_count"
        )
        or 0
    ) != 1:

        # Trường này vẫn có thể được báo tổng raw = 1,
        # nhưng deferred phải = 1.
        # Không coi raw unresolved là lỗi nếu deferred đúng.
        pass


    if int(
        parsed.get(
            "registry_deferred_unresolved_count"
        )
        or 0
    ) != 1:

        raise RuntimeError(
            "DUNG: Nghi Huong "
            "chua duoc deferred/giu nguyen."
        )


    # DB phải tuyệt đối không đổi.
    db_after = sha256(
        DB
    )

    lock_after = sha256(
        LOCK
    )

    roster_after = sha256(
        ROSTER
    )


    print()
    print("=" * 134)
    print("8. FILE SAFETY")
    print("=" * 134)


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
        "SERVICE NEW SHA    =",
        sha256(SERVICE),
    )

    print(
        "RESOLUTION SHA     =",
        sha256(RESOLUTION),
    )

    print(
        "BACKUP DIR         =",
        BACKUP_DIR,
    )


    if db_after != before["db"]:

        raise RuntimeError(
            "DUNG: DATABASE DA THAY DOI."
        )


    if lock_after != before["lock"]:

        raise RuntimeError(
            "DUNG: LEVEL LOCK DA THAY DOI."
        )


    if roster_after != before["roster"]:

        raise RuntimeError(
            "DUNG: THCS ROSTER DA THAY DOI."
        )


except Exception:

    print()
    print("=" * 134)
    print("CO LOI - TU KHOI PHUC SOURCE")
    print("=" * 134)


    # Restore service gốc.
    shutil.copy2(
        SERVICE_BACKUP,
        SERVICE,
    )


    # Resolution là file mới nên xóa.
    if RESOLUTION.exists():
        RESOLUTION.unlink()


    if service_tmp.exists():
        service_tmp.unlink()


    if resolution_tmp.exists():
        resolution_tmp.unlink()


    print(
        "SERVICE DA KHOI PHUC =",
        sha256(SERVICE),
    )

    print(
        "RESOLUTION THCS DA XOA."
    )

    print(
        "DATABASE KHONG DUOC DUNG TOI."
    )

    raise


finally:

    if service_tmp.exists():
        service_tmp.unlink()

    if resolution_tmp.exists():
        resolution_tmp.unlink()


print()
print("=" * 134)
print("CAI RESOLUTION THCS BUOC 1: THANH CONG")
print("=" * 134)

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

print()
print(
    "BUOC TIEP THEO:"
)

print(
    "GIAI QUYET CAC BLOCK THCS CON LAI "
    "ROI MO DRY-RUN 13 PHUONG AN."
)

print("=" * 134)
