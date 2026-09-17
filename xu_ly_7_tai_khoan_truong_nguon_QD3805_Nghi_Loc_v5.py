# -*- coding: utf-8 -*-
r"""
V5 - XỬ LÝ THẬT 7 TÀI KHOẢN TRƯỜNG NGUỒN SAU SÁP NHẬP QĐ 3805 - NGHI LỘC
============================================================================

MỤC TIÊU
--------
Chỉ sửa đúng 7 tài khoản cấp Trường của 7 trường nguồn đã được DRY-RUN V4.2 xác nhận:

    1) Trả school_id của tài khoản về đúng trường nguồn lịch sử.
    2) Đặt is_active = 0 để tài khoản Trường nguồn không còn đăng nhập.
    3) KHÔNG sửa username.
    4) KHÔNG sửa password_hash.
    5) KHÔNG sửa full_name.
    6) KHÔNG sửa role_id.
    7) KHÔNG sửa CBQL.
    8) KHÔNG sửa giáo viên.

Sau V5:
- Tài khoản Trường gốc của trường đích tiếp tục hoạt động.
- CBQL/GV trường nguồn đã sáp nhập vẫn thuộc trường đích.
- Tài khoản Trường nguồn được giữ lại tại trường cũ nhưng bị khóa, phục vụ dấu vết lịch sử.

AN TOÀN
-------
- Pre-flight kiểm tra chính xác ID / username / role_id / school_id / is_active.
- Kiểm tra 152 tài khoản nguồn vẫn đúng trạng thái V4.2.
- Tạo backup SQLite trước khi sửa.
- Toàn bộ UPDATE trong một transaction BEGIN IMMEDIATE.
- Nếu bất kỳ điều kiện nào sai: ROLLBACK.
- Sau UPDATE kiểm tra:
    + đúng 7 source school login về source và inactive;
    + mỗi target còn đúng 1 native school login active;
    + 145 CBQL/GV/khác không bị thay đổi;
    + source schools vẫn inactive;
    + target schools vẫn active;
    + foreign_key_check = 0;
    + integrity_check = ok.

CHẠY:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\xu_ly_7_tai_khoan_truong_nguon_QD3805_Nghi_Loc_v5.py

KẾT QUẢ:
    Backup:
        C:\PhoCap\backups\phocap_truoc_V5_tai_khoan_QD3805_Nghi_Loc_<timestamp>.db

    Báo cáo ZIP:
        C:\PhoCap\V5_tai_khoan_QD3805_Nghi_Loc_KET_QUA_<timestamp>.zip
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(r"C:\PhoCap")
DB_PATH = PROJECT_ROOT / "data" / "phocap.db"
BACKUP_DIR = PROJECT_ROOT / "backups"

# 7 tài khoản Trường nguồn được khóa bởi DRY-RUN V4.2.
# user_id: username, source_school_id, target_school_id, native_target_login_id, native_target_username
SOURCE_SCHOOL_ACCOUNTS = {
    12930: {
        "username": "truong_40429323",
        "source_school_id": 749,
        "target_school_id": 747,
        "native_target_login_id": 12935,
        "native_target_username": "truong_40429301",
        "source_school_name": "Trường MN Nghi Trung",
        "target_school_name": "Trường Mầm non TT Quán Hành",
    },
    12933: {
        "username": "truong_40429325",
        "source_school_id": 750,
        "target_school_id": 748,
        "native_target_login_id": 12932,
        "native_target_username": "truong_40429310",
        "source_school_name": "Trường Mầm non Nghi Hoa",
        "target_school_name": "Trường Mầm non Nghi Diên",
    },
    12934: {
        "username": "truong_40429332",
        "source_school_id": 751,
        "target_school_id": 748,
        "native_target_login_id": 12932,
        "native_target_username": "truong_40429310",
        "source_school_name": "Trường Mầm non Nghi Vạn",
        "target_school_name": "Trường Mầm non Nghi Diên",
    },
    13615: {
        "username": "truong_40429525",
        "source_school_id": 1607,
        "target_school_id": 1606,
        "native_target_login_id": 13616,
        "native_target_username": "truong_40429523",
        "source_school_name": "THCS Nghi Hoa",
        "target_school_name": "THCS Nghi Trung",
    },
    13617: {
        "username": "truong_40429532",
        "source_school_id": 1608,
        "target_school_id": 1605,
        "native_target_login_id": 13614,
        "native_target_username": "truong_40429510",
        "source_school_name": "THCS Nghi Vạn",
        "target_school_name": "THCS Nghi Diên",
    },
    14059: {
        "username": "truong_40429429",
        "source_school_id": 1180,
        "target_school_id": 1179,
        "native_target_login_id": 14057,
        "native_target_username": "truong_40429427",
        "source_school_name": "Trường Tiểu học Nghi Hoa",
        "target_school_name": "Trường TH Nghi Trung",
    },
    14060: {
        "username": "truong_40429436",
        "source_school_id": 1181,
        "target_school_id": 1178,
        "native_target_login_id": 14056,
        "native_target_username": "truong_40429412",
        "source_school_name": "Trường Tiểu học Nghi Vạn",
        "target_school_name": "Trường TH Nghi Diên",
    },
}

SOURCE_IDS = tuple(sorted({x["source_school_id"] for x in SOURCE_SCHOOL_ACCOUNTS.values()}))
TARGET_IDS = tuple(sorted({x["target_school_id"] for x in SOURCE_SCHOOL_ACCOUNTS.values()}))
SOURCE_LOGIN_IDS = tuple(sorted(SOURCE_SCHOOL_ACCOUNTS))
EXPECTED_ORIGIN_USERS = 152
EXPECTED_OTHER_USERS = EXPECTED_ORIGIN_USERS - len(SOURCE_LOGIN_IDS)

MERGE_MAP = {
    750: 748,
    751: 748,
    749: 747,
    1181: 1178,
    1180: 1179,
    1608: 1605,
    1607: 1606,
}


class FixAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def colset(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        r[1]
        for r in conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    }


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def fetch_user(conn: sqlite3.Connection, user_id: int):
    return conn.execute(
        "SELECT id, username, full_name, role_id, commune_id, school_id, "
        "is_active, created_at "
        "FROM users WHERE id=?",
        (user_id,),
    ).fetchone()


def fetch_all_users_min(conn: sqlite3.Connection) -> dict[int, tuple]:
    """
    Snapshot những trường V5 cam kết không sửa.
    Password/hash không được đọc và không được đụng tới.
    """
    rows = conn.execute(
        "SELECT id, username, full_name, role_id, commune_id, school_id, "
        "is_active, created_at FROM users"
    ).fetchall()
    return {
        int(r[0]): tuple(r)
        for r in rows
    }


def school_name(conn: sqlite3.Connection, school_id: int) -> str:
    cs = colset(conn, "schools")
    name_col = None
    for c in ("name", "school_name", "ten_truong"):
        if c in cs:
            name_col = c
            break
    if not name_col:
        return ""
    row = conn.execute(
        f"SELECT {qident(name_col)} FROM schools WHERE id=?",
        (school_id,),
    ).fetchone()
    return "" if not row else str(row[0])


def find_pre_merge_backup() -> Path:
    candidates = sorted(
        BACKUP_DIR.glob("phocap_truoc_sap_nhap_QD3805_Nghi_Loc_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FixAbort(
            r"Không tìm thấy backup trước sáp nhập trong C:\PhoCap\backups."
        )
    return candidates[0]


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def backup_database() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / (
        f"phocap_truoc_V5_tai_khoan_QD3805_Nghi_Loc_{ts}.db"
    )

    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(str(backup_path))
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            check.close()
            try:
                backup_path.unlink()
            except Exception:
                pass
            raise FixAbort(
                f"Backup V5 không đạt integrity_check: {integrity}"
            )
    finally:
        try:
            check.close()
        except Exception:
            pass

    return backup_path


def preflight_origin_users(
    conn: sqlite3.Connection,
    pre_merge_backup: Path,
) -> tuple[dict[int, tuple], list[dict]]:
    """
    Dùng backup trước sáp nhập để xác nhận lại đúng 152 user nguồn.
    Trả snapshot 145 user KHÔNG phải source school login để đảm bảo V5 không đụng.
    """
    bak = connect_ro(pre_merge_backup)
    try:
        rows = bak.execute(
            f"SELECT id, username, full_name, role_id, commune_id, school_id, "
            f"is_active, created_at "
            f"FROM users WHERE school_id IN ({markers(len(SOURCE_IDS))})",
            SOURCE_IDS,
        ).fetchall()

        if len(rows) != EXPECTED_ORIGIN_USERS:
            raise FixAbort(
                f"Backup trước sáp nhập có {len(rows)} users nguồn; "
                f"phải bằng {EXPECTED_ORIGIN_USERS}."
            )

        origin_ids = {int(r["id"]) for r in rows}
        if not set(SOURCE_LOGIN_IDS) <= origin_ids:
            missing = sorted(set(SOURCE_LOGIN_IDS) - origin_ids)
            raise FixAbort(
                f"7 source school login không khớp backup; thiếu IDs: {missing}"
            )

        other_ids = sorted(origin_ids - set(SOURCE_LOGIN_IDS))
        if len(other_ids) != EXPECTED_OTHER_USERS:
            raise FixAbort(
                f"Số user CBQL/GV/khác phải giữ nguyên={len(other_ids)}, "
                f"expected={EXPECTED_OTHER_USERS}"
            )

        snapshot = {}
        report = []
        for uid in other_ids:
            before_origin = next(r for r in rows if int(r["id"]) == uid)
            current = fetch_user(conn, uid)
            if current is None:
                raise FixAbort(f"User id={uid} không còn trong DB hiện tại.")

            source_sid = int(before_origin["school_id"])
            expected_target = MERGE_MAP[source_sid]
            if current["school_id"] != expected_target:
                raise FixAbort(
                    f"User id={uid} hiện school_id={current['school_id']}; "
                    f"expected target={expected_target}."
                )

            snapshot[uid] = tuple(current)
            report.append({
                "user_id": uid,
                "username": current["username"],
                "full_name": current["full_name"],
                "role_id": current["role_id"],
                "source_school_id_before_merger": source_sid,
                "current_target_school_id": current["school_id"],
                "is_active": current["is_active"],
                "v5_action": "KEEP_UNCHANGED",
            })

        return snapshot, report
    finally:
        bak.close()


def preflight(conn: sqlite3.Connection, pre_merge_backup: Path) -> dict:
    required_user_cols = {
        "id", "username", "full_name", "role_id",
        "commune_id", "school_id", "is_active", "created_at"
    }
    if not table_exists(conn, "users"):
        raise FixAbort("Không có bảng users.")
    missing = required_user_cols - colset(conn, "users")
    if missing:
        raise FixAbort(f"users thiếu cột: {sorted(missing)}")

    if not table_exists(conn, "schools"):
        raise FixAbort("Không có bảng schools.")
    school_cols = colset(conn, "schools")
    if not {"id", "is_active"} <= school_cols:
        raise FixAbort("schools thiếu id hoặc is_active.")

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise FixAbort(f"integrity_check trước V5={integrity}")

    # 1. 7 source login phải đúng chính xác trạng thái V4.2.
    source_login_before = []
    for uid, plan in SOURCE_SCHOOL_ACCOUNTS.items():
        r = fetch_user(conn, uid)
        if not r:
            raise FixAbort(f"Không tìm thấy source school login id={uid}")

        checks = {
            "username": (r["username"], plan["username"]),
            "role_id": (r["role_id"], 3),
            "school_id": (r["school_id"], plan["target_school_id"]),
            "is_active": (r["is_active"], 1),
        }
        bad = [
            f"{k}: actual={actual!r} expected={expected!r}"
            for k, (actual, expected) in checks.items()
            if actual != expected
        ]
        if bad:
            raise FixAbort(
                f"Source school login id={uid} đã khác V4.2: " + "; ".join(bad)
            )

        source_login_before.append({
            "user_id": uid,
            "username": r["username"],
            "full_name": r["full_name"],
            "role_id": r["role_id"],
            "source_school_id": plan["source_school_id"],
            "source_school_name": school_name(conn, plan["source_school_id"]),
            "current_target_school_id": r["school_id"],
            "target_school_name": school_name(conn, plan["target_school_id"]),
            "is_active_before": r["is_active"],
        })

    # 2. Native target login phải tồn tại và active.
    native_target_before = []
    checked_native_ids = set()
    for plan in SOURCE_SCHOOL_ACCOUNTS.values():
        nid = plan["native_target_login_id"]
        if nid in checked_native_ids:
            continue
        checked_native_ids.add(nid)

        r = fetch_user(conn, nid)
        if not r:
            raise FixAbort(f"Không tìm thấy native target school login id={nid}")
        bad = []
        if r["username"] != plan["native_target_username"]:
            bad.append(
                f"username={r['username']!r} expected={plan['native_target_username']!r}"
            )
        if r["role_id"] != 3:
            bad.append(f"role_id={r['role_id']} expected=3")
        if r["school_id"] != plan["target_school_id"]:
            bad.append(
                f"school_id={r['school_id']} expected={plan['target_school_id']}"
            )
        if r["is_active"] != 1:
            bad.append(f"is_active={r['is_active']} expected=1")
        if bad:
            raise FixAbort(
                f"Native target login id={nid} sai: " + "; ".join(bad)
            )

        native_target_before.append({
            "user_id": nid,
            "username": r["username"],
            "full_name": r["full_name"],
            "role_id": r["role_id"],
            "school_id": r["school_id"],
            "school_name": school_name(conn, r["school_id"]),
            "is_active": r["is_active"],
        })

    # 3. School source phải inactive, target phải active.
    for sid in SOURCE_IDS:
        r = conn.execute(
            "SELECT is_active FROM schools WHERE id=?", (sid,)
        ).fetchone()
        if not r:
            raise FixAbort(f"Không tìm thấy source school id={sid}")
        if r[0] != 0:
            raise FixAbort(
                f"Source school id={sid} phải is_active=0 nhưng hiện={r[0]}"
            )

    for sid in TARGET_IDS:
        r = conn.execute(
            "SELECT is_active FROM schools WHERE id=?", (sid,)
        ).fetchone()
        if not r:
            raise FixAbort(f"Không tìm thấy target school id={sid}")
        if r[0] != 1:
            raise FixAbort(
                f"Target school id={sid} phải is_active=1 nhưng hiện={r[0]}"
            )

    other_snapshot, other_report = preflight_origin_users(
        conn, pre_merge_backup
    )

    return {
        "source_login_before": source_login_before,
        "native_target_before": native_target_before,
        "other_snapshot": other_snapshot,
        "other_report": other_report,
    }


def verify_target_login_counts(conn: sqlite3.Connection) -> list[dict]:
    """
    Sau V5, mỗi target phải còn đúng 1 tài khoản truong_ active.
    """
    report = []
    expected_native = {
        plan["target_school_id"]: (
            plan["native_target_login_id"],
            plan["native_target_username"],
        )
        for plan in SOURCE_SCHOOL_ACCOUNTS.values()
    }

    for target_id in TARGET_IDS:
        rows = conn.execute(
            "SELECT id, username, school_id, is_active "
            "FROM users "
            "WHERE school_id=? AND username LIKE 'truong_%' "
            "ORDER BY id",
            (target_id,),
        ).fetchall()

        active_rows = [r for r in rows if r["is_active"] == 1]
        native_id, native_username = expected_native[target_id]

        ok = (
            len(rows) == 1
            and len(active_rows) == 1
            and rows[0]["id"] == native_id
            and rows[0]["username"] == native_username
        )
        report.append({
            "target_school_id": target_id,
            "target_school_name": school_name(conn, target_id),
            "school_login_count_after": len(rows),
            "active_school_login_count_after": len(active_rows),
            "school_login_ids_after": ",".join(str(r["id"]) for r in rows),
            "school_login_usernames_after": ",".join(str(r["username"]) for r in rows),
            "expected_native_id": native_id,
            "expected_native_username": native_username,
            "result": "PASS" if ok else "FAIL",
        })

    return report


def run_fix() -> None:
    print("=" * 100)
    print("V5 - XỬ LÝ THẬT 7 TÀI KHOẢN TRƯỜNG NGUỒN QĐ 3805 - NGHI LỘC")
    print("=" * 100)
    print("Chỉ sửa 7 tài khoản 'truong_' nguồn. CBQL/GV KHÔNG bị sửa.")

    if not DB_PATH.exists():
        raise FixAbort(f"Không tìm thấy database: {DB_PATH}")

    pre_merge_backup = find_pre_merge_backup()
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = PROJECT_ROOT / f"V5_tai_khoan_QD3805_Nghi_Loc_{ts}"
    report_dir.mkdir(parents=True, exist_ok=False)

    v5_backup = None
    committed = False

    try:
        state = preflight(conn, pre_merge_backup)

        print("PRE-FLIGHT PASS")
        print("  7/7 source school login khớp V4.2")
        print("  6/6 native target school login đang active")
        print(f"  {EXPECTED_OTHER_USERS} CBQL/GV/khác sẽ được giữ nguyên")
        print("  Source schools inactive / target schools active: PASS")

        write_csv(
            report_dir / "01_7_TAI_KHOAN_TRUONG_TRUOC_V5.csv",
            [
                "user_id", "username", "full_name", "role_id",
                "source_school_id", "source_school_name",
                "current_target_school_id", "target_school_name",
                "is_active_before",
            ],
            state["source_login_before"],
        )
        write_csv(
            report_dir / "02_NATIVE_TARGET_LOGIN_TRUOC_V5.csv",
            [
                "user_id", "username", "full_name", "role_id",
                "school_id", "school_name", "is_active",
            ],
            state["native_target_before"],
        )
        write_csv(
            report_dir / "03_145_CBQL_GV_KHAC_GIU_NGUYEN.csv",
            [
                "user_id", "username", "full_name", "role_id",
                "source_school_id_before_merger",
                "current_target_school_id", "is_active", "v5_action",
            ],
            state["other_report"],
        )

        # Backup V5.
        v5_backup = backup_database()
        print(f"BACKUP V5 OK: {v5_backup}")

        conn.execute("BEGIN IMMEDIATE")

        update_rows = []
        for uid, plan in SOURCE_SCHOOL_ACCOUNTS.items():
            cur = conn.execute(
                "UPDATE users "
                "SET school_id=?, is_active=0 "
                "WHERE id=? "
                "AND username=? "
                "AND role_id=3 "
                "AND school_id=? "
                "AND is_active=1",
                (
                    plan["source_school_id"],
                    uid,
                    plan["username"],
                    plan["target_school_id"],
                ),
            )

            if cur.rowcount != 1:
                raise FixAbort(
                    f"UPDATE user_id={uid} rowcount={cur.rowcount}; phải bằng 1."
                )

            update_rows.append({
                "user_id": uid,
                "username": plan["username"],
                "source_school_id_after": plan["source_school_id"],
                "source_school_name": plan["source_school_name"],
                "old_target_school_id": plan["target_school_id"],
                "old_target_school_name": plan["target_school_name"],
                "is_active_after": 0,
                "action": "RETURN_TO_SOURCE_AND_DISABLE",
            })

        # POST-CHECK A: 7 source login về đúng source, inactive.
        seven_after = []
        for uid, plan in SOURCE_SCHOOL_ACCOUNTS.items():
            r = fetch_user(conn, uid)
            if not r:
                raise FixAbort(f"User id={uid} biến mất sau UPDATE.")
            if r["school_id"] != plan["source_school_id"]:
                raise FixAbort(
                    f"User id={uid} school_id sau V5={r['school_id']}; "
                    f"expected source={plan['source_school_id']}"
                )
            if r["is_active"] != 0:
                raise FixAbort(
                    f"User id={uid} is_active sau V5={r['is_active']}; expected=0"
                )
            if r["username"] != plan["username"] or r["role_id"] != 3:
                raise FixAbort(
                    f"User id={uid} username/role_id bị thay đổi ngoài dự kiến."
                )

            seven_after.append({
                "user_id": uid,
                "username": r["username"],
                "full_name": r["full_name"],
                "role_id": r["role_id"],
                "school_id_after": r["school_id"],
                "school_name_after": school_name(conn, r["school_id"]),
                "is_active_after": r["is_active"],
                "result": "PASS",
            })

        # POST-CHECK B: 145 user phải giống hệt snapshot trước V5.
        changed_other = []
        for uid, before_tuple in state["other_snapshot"].items():
            r = fetch_user(conn, uid)
            if not r:
                changed_other.append({
                    "user_id": uid,
                    "detail": "User missing after V5",
                })
                continue
            after_tuple = tuple(r)
            if after_tuple != before_tuple:
                changed_other.append({
                    "user_id": uid,
                    "detail": (
                        f"before={before_tuple}; after={after_tuple}"
                    ),
                })

        if changed_other:
            raise FixAbort(
                f"V5 làm thay đổi {len(changed_other)} user ngoài 7 tài khoản Trường."
            )

        # POST-CHECK C: target còn đúng native login.
        target_login_report = verify_target_login_counts(conn)
        bad_targets = [r for r in target_login_report if r["result"] != "PASS"]
        if bad_targets:
            raise FixAbort(
                f"Có {len(bad_targets)} target không còn đúng 1 native school login."
            )

        # POST-CHECK D: source school vẫn inactive / target active.
        for sid in SOURCE_IDS:
            r = conn.execute(
                "SELECT is_active FROM schools WHERE id=?", (sid,)
            ).fetchone()
            if not r or r[0] != 0:
                raise FixAbort(
                    f"Source school id={sid} không còn is_active=0."
                )

        for sid in TARGET_IDS:
            r = conn.execute(
                "SELECT is_active FROM schools WHERE id=?", (sid,)
            ).fetchone()
            if not r or r[0] != 1:
                raise FixAbort(
                    f"Target school id={sid} không còn is_active=1."
                )

        # POST-CHECK E: FK.
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise FixAbort(
                f"foreign_key_check có {len(fk_errors)} lỗi."
            )

        # Tất cả PASS -> COMMIT.
        conn.commit()
        committed = True

        integrity_after = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity_after != "ok":
            raise FixAbort(
                "ĐÃ COMMIT nhưng integrity_check sau V5 không ok: "
                f"{integrity_after}. Backup V5: {v5_backup}"
            )

        write_csv(
            report_dir / "10_UPDATE_DA_THUC_HIEN.csv",
            [
                "user_id", "username",
                "source_school_id_after", "source_school_name",
                "old_target_school_id", "old_target_school_name",
                "is_active_after", "action",
            ],
            update_rows,
        )
        write_csv(
            report_dir / "11_7_TAI_KHOAN_TRUONG_SAU_V5.csv",
            [
                "user_id", "username", "full_name", "role_id",
                "school_id_after", "school_name_after",
                "is_active_after", "result",
            ],
            seven_after,
        )
        write_csv(
            report_dir / "12_TARGET_CHI_CON_1_NATIVE_LOGIN.csv",
            [
                "target_school_id", "target_school_name",
                "school_login_count_after",
                "active_school_login_count_after",
                "school_login_ids_after",
                "school_login_usernames_after",
                "expected_native_id",
                "expected_native_username",
                "result",
            ],
            target_login_report,
        )
        write_csv(
            report_dir / "13_USER_NGOAI_7_BI_THAY_DOI.csv",
            ["user_id", "detail"],
            changed_other,
        )

        summary = report_dir / "00_KET_QUA_V5.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write("V5 - KẾT QUẢ XỬ LÝ 7 TÀI KHOẢN TRƯỜNG NGUỒN QĐ 3805\n")
            f.write("=" * 100 + "\n")
            f.write("STATUS = SUCCESS\n")
            f.write(f"Database: {DB_PATH}\n")
            f.write(f"Backup trước V5: {v5_backup}\n")
            f.write(f"Backup trước sáp nhập dùng đối chiếu: {pre_merge_backup}\n\n")

            f.write("1. THAY ĐỔI\n")
            f.write("- 7/7 tài khoản Trường nguồn: school_id trả về source + is_active=0.\n")
            f.write("- Username: không đổi.\n")
            f.write("- Full name: không đổi.\n")
            f.write("- Role ID: không đổi.\n")
            f.write("- Password/hash: không đọc, không sửa.\n\n")

            f.write("2. GIỮ NGUYÊN\n")
            f.write(f"- {EXPECTED_OTHER_USERS} CBQL/GV/khác: không thay đổi.\n")
            f.write("- 6 native target school login: tiếp tục active.\n")
            f.write("- 7 source schools: tiếp tục inactive.\n")
            f.write("- 6 target schools nhận sáp nhập: tiếp tục active.\n\n")

            f.write("3. KIỂM TRA\n")
            f.write("- 7 source school login sau V5: PASS.\n")
            f.write("- Mỗi target còn đúng 1 native school login: PASS.\n")
            f.write("- User ngoài 7 bị thay đổi: 0.\n")
            f.write("- foreign_key_check: PASS (0 lỗi).\n")
            f.write(f"- integrity_check sau commit: {integrity_after}\n")

        zip_path = PROJECT_ROOT / (
            f"V5_tai_khoan_QD3805_Nghi_Loc_KET_QUA_{ts}.zip"
        )
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(report_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 100)
        print("V5 THÀNH CÔNG")
        print("=" * 100)
        print("7/7 tài khoản Trường nguồn đã trả về trường cũ và khóa is_active=0.")
        print(f"{EXPECTED_OTHER_USERS} CBQL/GV/khác: KHÔNG bị thay đổi.")
        print("Mỗi trường đích còn đúng 1 tài khoản Trường gốc active.")
        print("foreign_key_check: PASS")
        print("integrity_check: PASS")
        print(f"Backup V5: {v5_backup}")
        print(f"ZIP kết quả: {zip_path}")
        print()
        print("GỬI LẠI ZIP KẾT QUẢ V5 CHO TÔI ĐỂ ĐỐI CHIẾU.")

    except Exception:
        if not committed:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        conn.close()


def main() -> None:
    try:
        run_fix()
    except FixAbort as e:
        print()
        print("=" * 100)
        print("V5 ĐÃ DỪNG - ĐÃ ROLLBACK NẾU CHƯA COMMIT")
        print("=" * 100)
        print(str(e))
        print("Không tiếp tục sửa database.")
        sys.exit(2)
    except sqlite3.IntegrityError as e:
        print()
        print("=" * 100)
        print("LỖI INTEGRITY/UNIQUE/FK - ĐÃ ROLLBACK")
        print("=" * 100)
        print(repr(e))
        sys.exit(3)
    except sqlite3.Error as e:
        print()
        print("=" * 100)
        print("LỖI SQLITE - ĐÃ ROLLBACK NẾU CHƯA COMMIT")
        print("=" * 100)
        print(repr(e))
        sys.exit(4)
    except Exception as e:
        print()
        print("=" * 100)
        print("LỖI KHÔNG DỰ KIẾN")
        print("=" * 100)
        print(repr(e))
        print("Nếu lỗi xảy ra trước COMMIT thì transaction đã rollback.")
        sys.exit(5)


if __name__ == "__main__":
    main()
