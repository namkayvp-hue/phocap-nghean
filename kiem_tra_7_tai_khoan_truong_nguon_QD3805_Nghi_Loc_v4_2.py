# -*- coding: utf-8 -*-
"""
DRY-RUN V4.2 - XÁC NHẬN 7 TÀI KHOẢN TRƯỜNG NGUỒN QĐ 3805 - NGHI LỘC
====================================================================

MỤC TIÊU
--------
- CHỈ ĐỌC database hiện tại và backup trước sáp nhập.
- KHÔNG SỬA phocap.db.
- Xác nhận chính xác 7 tài khoản cấp Trường của 7 trường nguồn.
- PHÂN BIỆT:
    + Tài khoản Trường: username bắt đầu "truong_"
    + CBQL: username bắt đầu "cbql."
    + Giáo viên: các tài khoản còn lại (thường "gv.")
- Không dùng role_id=3 để khóa hàng loạt vì role_id=3 gồm cả CBQL và tài khoản Trường.
- Kiểm tra mỗi trường đích đã có tài khoản "truong_" gốc từ trước sáp nhập.
- Đề xuất cho V5:
    + 7 tài khoản Trường nguồn: trả school_id về trường nguồn + is_active=0
    + CBQL và GV: GIỮ school_id tại trường đích + giữ is_active hiện tại
- Tạo cổng SAFE_TO_FIX_ACCOUNTS.

CHẠY:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_7_tai_khoan_truong_nguon_QD3805_Nghi_Loc_v4_2.py

KẾT QUẢ:
    C:\PhoCap\dry_run_7_tai_khoan_truong_nguon_QD3805_Nghi_Loc_v4_2_<timestamp>.zip
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(r"C:\PhoCap")
CURRENT_DB = PROJECT_ROOT / "data" / "phocap.db"
BACKUP_DIR = PROJECT_ROOT / "backups"

MERGE_MAP = {
    750: 748,    # MN Nghi Hoa -> MN Nghi Dien
    751: 748,    # MN Nghi Van -> MN Nghi Dien
    749: 747,    # MN Nghi Trung -> MN TT Quan Hanh
    1181: 1178,  # TH Nghi Van -> TH Nghi Dien
    1180: 1179,  # TH Nghi Hoa -> TH Nghi Trung
    1608: 1605,  # THCS Nghi Van -> THCS Nghi Dien
    1607: 1606,  # THCS Nghi Hoa -> THCS Nghi Trung
}

SOURCE_IDS = tuple(MERGE_MAP.keys())
TARGET_IDS = tuple(sorted(set(MERGE_MAP.values())))
EXPECTED_MOVED_USERS = 152
EXPECTED_SOURCE_SCHOOL_ACCOUNTS = 7


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


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


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        r[1]
        for r in conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    }


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


def school_names(conn: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(conn, "schools"):
        return {}
    cs = columns(conn, "schools")
    name_col = None
    for c in ("name", "school_name", "ten_truong"):
        if c in cs:
            name_col = c
            break
    if not name_col:
        return {}
    ids = sorted(set(SOURCE_IDS) | set(TARGET_IDS))
    marks = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, {qident(name_col)} FROM schools WHERE id IN ({marks})",
        ids,
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def roles(conn: sqlite3.Connection) -> list[dict]:
    if not table_exists(conn, "roles"):
        raise AuditAbort("Không có bảng roles.")
    cs = columns(conn, "roles")
    wanted = [c for c in ("id", "code", "name", "description") if c in cs]
    if "id" not in wanted:
        raise AuditAbort("Bảng roles không có id.")
    rows = conn.execute(
        "SELECT " + ", ".join(qident(c) for c in wanted) + " FROM roles ORDER BY id"
    ).fetchall()
    return [{c: r[c] for c in wanted} for r in rows]


def fetch_users(conn: sqlite3.Connection) -> dict[int, dict]:
    if not table_exists(conn, "users"):
        raise AuditAbort("Không có bảng users.")
    cs = columns(conn, "users")
    required = {"id", "username", "full_name", "role_id", "school_id", "is_active"}
    missing = required - cs
    if missing:
        raise AuditAbort(f"users thiếu cột: {sorted(missing)}")

    rows = conn.execute(
        "SELECT id, username, full_name, role_id, commune_id, school_id, "
        "is_active, created_at FROM users"
    ).fetchall()
    return {
        int(r["id"]): {
            "id": int(r["id"]),
            "username": r["username"],
            "full_name": r["full_name"],
            "role_id": r["role_id"],
            "commune_id": r["commune_id"],
            "school_id": r["school_id"],
            "is_active": r["is_active"],
            "created_at": r["created_at"],
        }
        for r in rows
    }


def account_kind(username: str | None) -> str:
    u = (username or "").strip().lower()
    if u.startswith("truong_"):
        return "SCHOOL_LOGIN"
    if u.startswith("cbql."):
        return "CBQL"
    if u.startswith("gv."):
        return "TEACHER"
    return "OTHER"


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def audit() -> None:
    print("=" * 100)
    print("DRY-RUN V4.2 - XÁC NHẬN 7 TÀI KHOẢN TRƯỜNG NGUỒN QĐ 3805 - NGHI LỘC")
    print("=" * 100)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not CURRENT_DB.exists():
        raise AuditAbort(f"Không tìm thấy current DB: {CURRENT_DB}")
    backup_db = find_backup()

    cur = connect_ro(CURRENT_DB)
    bak = connect_ro(backup_db)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / f"dry_run_7_tai_khoan_truong_nguon_QD3805_Nghi_Loc_v4_2_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        int_cur = cur.execute("PRAGMA integrity_check").fetchone()[0]
        int_bak = bak.execute("PRAGMA integrity_check").fetchone()[0]
        if int_cur != "ok":
            raise AuditAbort(f"Current DB integrity_check={int_cur}")
        if int_bak != "ok":
            raise AuditAbort(f"Backup DB integrity_check={int_bak}")

        names_bak = school_names(bak)
        names_cur = school_names(cur)
        role_rows = roles(cur)

        users_bak = fetch_users(bak)
        users_cur = fetch_users(cur)

        # 152 tài khoản có nguồn gốc từ 7 trường nguồn.
        source_user_ids = sorted(
            uid for uid, u in users_bak.items()
            if u["school_id"] in SOURCE_IDS
        )

        moved_rows = []
        anomalies = []
        kind_counter = Counter()

        for uid in source_user_ids:
            before = users_bak[uid]
            after = users_cur.get(uid)
            source_id = int(before["school_id"])
            target_id = MERGE_MAP[source_id]
            kind = account_kind(before["username"])
            kind_counter[kind] += 1

            if after is None:
                anomalies.append({
                    "type": "MISSING_USER",
                    "user_id": uid,
                    "username": before["username"],
                    "detail": "Có trong backup nhưng không còn trong current DB",
                })
                continue

            if after["school_id"] != target_id:
                anomalies.append({
                    "type": "WRONG_TARGET",
                    "user_id": uid,
                    "username": before["username"],
                    "detail": (
                        f"source={source_id}; expected_target={target_id}; "
                        f"current={after['school_id']}"
                    ),
                })

            if before["role_id"] != after["role_id"]:
                anomalies.append({
                    "type": "ROLE_CHANGED",
                    "user_id": uid,
                    "username": before["username"],
                    "detail": (
                        f"role_before={before['role_id']}; "
                        f"role_after={after['role_id']}"
                    ),
                })

            moved_rows.append({
                "user_id": uid,
                "username": before["username"],
                "full_name": before["full_name"],
                "role_id": before["role_id"],
                "account_kind": kind,
                "source_school_id": source_id,
                "source_school_name": names_bak.get(source_id, ""),
                "target_school_id": target_id,
                "target_school_name": names_cur.get(target_id, ""),
                "current_school_id": after["school_id"],
                "is_active_before": before["is_active"],
                "is_active_after": after["is_active"],
            })

        source_school_logins = [
            r for r in moved_rows if r["account_kind"] == "SCHOOL_LOGIN"
        ]
        source_cbql = [
            r for r in moved_rows if r["account_kind"] == "CBQL"
        ]
        source_teachers = [
            r for r in moved_rows if r["account_kind"] == "TEACHER"
        ]
        source_other = [
            r for r in moved_rows if r["account_kind"] == "OTHER"
        ]

        # Phải đúng 1 school login cho mỗi source trong backup.
        source_login_by_school = defaultdict(list)
        for r in source_school_logins:
            source_login_by_school[int(r["source_school_id"])].append(r)

        source_login_coverage = []
        for source_id in SOURCE_IDS:
            items = source_login_by_school.get(source_id, [])
            source_login_coverage.append({
                "source_school_id": source_id,
                "source_school_name": names_bak.get(source_id, ""),
                "target_school_id": MERGE_MAP[source_id],
                "target_school_name": names_cur.get(MERGE_MAP[source_id], ""),
                "school_login_count": len(items),
                "school_login_ids": ",".join(str(x["user_id"]) for x in items),
                "school_login_usernames": ",".join(str(x["username"]) for x in items),
                "result": "PASS" if len(items) == 1 else "FAIL",
            })

        # Tài khoản trường gốc của các target trong BACKUP.
        native_target_logins = defaultdict(list)
        for uid, u in users_bak.items():
            sid = u["school_id"]
            if sid in TARGET_IDS and account_kind(u["username"]) == "SCHOOL_LOGIN":
                native_target_logins[int(sid)].append(u)

        # Tài khoản trường đang hiện tại trên target CURRENT (bao gồm source login đã bị chuyển).
        current_target_logins = defaultdict(list)
        for uid, u in users_cur.items():
            sid = u["school_id"]
            if sid in TARGET_IDS and account_kind(u["username"]) == "SCHOOL_LOGIN":
                current_target_logins[int(sid)].append(u)

        target_checks = []
        for target_id in TARGET_IDS:
            native = sorted(native_target_logins.get(target_id, []), key=lambda x: x["id"])
            current = sorted(current_target_logins.get(target_id, []), key=lambda x: x["id"])
            incoming = sorted(
                [r for r in source_school_logins if int(r["target_school_id"]) == target_id],
                key=lambda x: x["user_id"],
            )
            target_checks.append({
                "target_school_id": target_id,
                "target_school_name": names_cur.get(target_id, ""),
                "native_login_count_before": len(native),
                "native_login_ids_before": ",".join(str(x["id"]) for x in native),
                "native_login_usernames_before": ",".join(str(x["username"]) for x in native),
                "incoming_source_login_count": len(incoming),
                "incoming_source_login_ids": ",".join(str(x["user_id"]) for x in incoming),
                "current_login_count": len(current),
                "current_login_ids": ",".join(str(x["id"]) for x in current),
                "result": "PASS" if len(native) == 1 else "FAIL",
            })

        # Kế hoạch V5 cho đúng 7 source school login.
        fix_plan = []
        for r in sorted(source_school_logins, key=lambda x: x["user_id"]):
            target_id = int(r["target_school_id"])
            native = native_target_logins.get(target_id, [])
            safe_one_native = len(native) == 1
            fix_plan.append({
                "user_id": r["user_id"],
                "username": r["username"],
                "full_name": r["full_name"],
                "role_id": r["role_id"],
                "source_school_id": r["source_school_id"],
                "source_school_name": r["source_school_name"],
                "current_school_id": r["current_school_id"],
                "target_school_id": r["target_school_id"],
                "target_school_name": r["target_school_name"],
                "current_is_active": r["is_active_after"],
                "native_target_login_id": native[0]["id"] if safe_one_native else "",
                "native_target_login_username": native[0]["username"] if safe_one_native else "",
                "proposed_school_id_after_v5": r["source_school_id"],
                "proposed_is_active_after_v5": 0,
                "proposed_action": (
                    "RETURN_TO_SOURCE_AND_DISABLE"
                    if safe_one_native else
                    "MANUAL_REVIEW"
                ),
                "reason": (
                    "Giữ tài khoản Trường nguồn làm dấu vết tại trường cũ nhưng khóa đăng nhập; "
                    "trường đích đã có tài khoản Trường gốc riêng."
                    if safe_one_native else
                    "Không xác nhận được đúng 1 tài khoản Trường gốc tại trường đích."
                ),
            })

        # Kế hoạch giữ nguyên CBQL/GV.
        keep_rows = []
        for r in moved_rows:
            if r["account_kind"] in ("CBQL", "TEACHER"):
                keep_rows.append({
                    "user_id": r["user_id"],
                    "username": r["username"],
                    "full_name": r["full_name"],
                    "account_kind": r["account_kind"],
                    "role_id": r["role_id"],
                    "source_school_id": r["source_school_id"],
                    "target_school_id": r["target_school_id"],
                    "current_school_id": r["current_school_id"],
                    "is_active_after": r["is_active_after"],
                    "proposed_action": "KEEP_AT_TARGET_UNCHANGED",
                })

        # Gate V5.
        role_map = {int(r["id"]): r for r in role_rows if r.get("id") is not None}
        source_school_role_ids = sorted({int(r["role_id"]) for r in source_school_logins})
        cbql_role_ids = sorted({int(r["role_id"]) for r in source_cbql})

        gate_checks = [
            {
                "check": "integrity_current",
                "result": "PASS" if int_cur == "ok" else "FAIL",
                "detail": str(int_cur),
            },
            {
                "check": "integrity_backup",
                "result": "PASS" if int_bak == "ok" else "FAIL",
                "detail": str(int_bak),
            },
            {
                "check": "152_users_origin_match",
                "result": "PASS" if len(source_user_ids) == EXPECTED_MOVED_USERS else "FAIL",
                "detail": f"found={len(source_user_ids)} expected={EXPECTED_MOVED_USERS}",
            },
            {
                "check": "no_user_move_anomalies",
                "result": "PASS" if not anomalies else "FAIL",
                "detail": f"anomalies={len(anomalies)}",
            },
            {
                "check": "exactly_7_source_school_logins",
                "result": "PASS" if len(source_school_logins) == EXPECTED_SOURCE_SCHOOL_ACCOUNTS else "FAIL",
                "detail": f"found={len(source_school_logins)} expected=7",
            },
            {
                "check": "one_school_login_per_source",
                "result": "PASS" if all(x["result"] == "PASS" for x in source_login_coverage) else "FAIL",
                "detail": "7 source schools checked",
            },
            {
                "check": "one_native_school_login_per_target",
                "result": "PASS" if all(x["result"] == "PASS" for x in target_checks) else "FAIL",
                "detail": f"targets={len(TARGET_IDS)}",
            },
            {
                "check": "no_unclassified_source_account",
                "result": "PASS" if not source_other else "FAIL",
                "detail": f"OTHER={len(source_other)}",
            },
            {
                "check": "school_login_and_cbql_share_role_but_are_distinguished_by_username",
                "result": (
                    "PASS"
                    if source_school_role_ids == cbql_role_ids and len(source_school_role_ids) == 1
                    else "FAIL"
                ),
                "detail": (
                    f"school_login_role_ids={source_school_role_ids}; "
                    f"cbql_role_ids={cbql_role_ids}"
                ),
            },
            {
                "check": "all_7_fix_plan_rows_safe",
                "result": "PASS" if all(
                    x["proposed_action"] == "RETURN_TO_SOURCE_AND_DISABLE"
                    for x in fix_plan
                ) and len(fix_plan) == 7 else "FAIL",
                "detail": f"safe_rows={sum(x['proposed_action']=='RETURN_TO_SOURCE_AND_DISABLE' for x in fix_plan)}/7",
            },
        ]
        safe = all(x["result"] == "PASS" for x in gate_checks)

        # Reports
        write_csv(
            out_dir / "60_ROLES.csv",
            ["id", "code", "name", "description"],
            role_rows,
        )
        write_csv(
            out_dir / "61_152_USERS_PHAN_LOAI.csv",
            [
                "user_id", "username", "full_name", "role_id", "account_kind",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "current_school_id", "is_active_before", "is_active_after",
            ],
            moved_rows,
        )
        write_csv(
            out_dir / "62_7_TAI_KHOAN_TRUONG_NGUON.csv",
            [
                "user_id", "username", "full_name", "role_id",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "current_school_id", "is_active_after",
            ],
            source_school_logins,
        )
        write_csv(
            out_dir / "63_CBQL_NGUON_GIU_O_TRUONG_DICH.csv",
            [
                "user_id", "username", "full_name", "role_id",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "current_school_id", "is_active_after",
            ],
            source_cbql,
        )
        write_csv(
            out_dir / "64_GIAO_VIEN_NGUON_GIU_O_TRUONG_DICH.csv",
            [
                "user_id", "username", "full_name", "role_id",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "current_school_id", "is_active_after",
            ],
            source_teachers,
        )
        write_csv(
            out_dir / "65_KIEM_TRA_1_LOGIN_TRUONG_MOI_SOURCE.csv",
            [
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "school_login_count", "school_login_ids",
                "school_login_usernames", "result",
            ],
            source_login_coverage,
        )
        write_csv(
            out_dir / "66_KIEM_TRA_LOGIN_GOC_TRUONG_DICH.csv",
            [
                "target_school_id", "target_school_name",
                "native_login_count_before", "native_login_ids_before",
                "native_login_usernames_before",
                "incoming_source_login_count", "incoming_source_login_ids",
                "current_login_count", "current_login_ids", "result",
            ],
            target_checks,
        )
        write_csv(
            out_dir / "67_KE_HOACH_V5_CHI_7_TAI_KHOAN_TRUONG_NGUON.csv",
            [
                "user_id", "username", "full_name", "role_id",
                "source_school_id", "source_school_name",
                "current_school_id",
                "target_school_id", "target_school_name",
                "current_is_active",
                "native_target_login_id", "native_target_login_username",
                "proposed_school_id_after_v5", "proposed_is_active_after_v5",
                "proposed_action", "reason",
            ],
            fix_plan,
        )
        write_csv(
            out_dir / "68_KE_HOACH_GIU_NGUYEN_CBQL_GV.csv",
            [
                "user_id", "username", "full_name", "account_kind", "role_id",
                "source_school_id", "target_school_id",
                "current_school_id", "is_active_after", "proposed_action",
            ],
            keep_rows,
        )
        write_csv(
            out_dir / "69_BAT_THUONG.csv",
            ["type", "user_id", "username", "detail"],
            anomalies,
        )
        write_csv(
            out_dir / "70_CONG_AN_TOAN_V5.csv",
            ["check", "result", "detail"],
            gate_checks,
        )

        summary = out_dir / "00_TONG_QUAN_V4_2.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write("DRY-RUN V4.2 - XÁC NHẬN 7 TÀI KHOẢN TRƯỜNG NGUỒN QĐ 3805\n")
            f.write("=" * 100 + "\n")
            f.write("CHẾ ĐỘ: CHỈ ĐỌC - KHÔNG SỬA DATABASE\n")
            f.write(f"Current DB: {CURRENT_DB}\n")
            f.write(f"Backup DB : {backup_db}\n\n")

            f.write("1. PHÂN LOẠI 152 TÀI KHOẢN NGUỒN\n")
            f.write(f"- Tổng: {len(moved_rows)}\n")
            f.write(f"- SCHOOL_LOGIN (truong_): {len(source_school_logins)}\n")
            f.write(f"- CBQL (cbql.): {len(source_cbql)}\n")
            f.write(f"- TEACHER (gv.): {len(source_teachers)}\n")
            f.write(f"- OTHER: {len(source_other)}\n")
            f.write(f"- Bất thường: {len(anomalies)}\n\n")

            f.write("2. 7 TÀI KHOẢN TRƯỜNG NGUỒN\n")
            for r in sorted(source_school_logins, key=lambda x: x["source_school_id"]):
                f.write(
                    f"- id={r['user_id']} | {r['username']} | {r['full_name']} | "
                    f"{r['source_school_name']} -> {r['target_school_name']}\n"
                )

            f.write("\n3. TÀI KHOẢN TRƯỜNG GỐC CỦA TRƯỜNG ĐÍCH\n")
            for r in target_checks:
                f.write(
                    f"- {r['target_school_id']} {r['target_school_name']}: "
                    f"native_before={r['native_login_count_before']}; "
                    f"incoming={r['incoming_source_login_count']}; "
                    f"current_total={r['current_login_count']}; "
                    f"{r['result']}\n"
                )

            f.write("\n4. KẾ HOẠCH V5\n")
            f.write(
                "- Chỉ 7 account username 'truong_' của trường nguồn: "
                "trả school_id về source và đặt is_active=0.\n"
            )
            f.write(
                "- CBQL và giáo viên: giữ nguyên school_id tại trường đích, "
                "không khóa.\n"
            )
            f.write(
                "- Không sửa username, password_hash, full_name, role_id.\n"
            )

            f.write("\n5. CỔNG AN TOÀN\n")
            for g in gate_checks:
                f.write(f"- [{g['result']}] {g['check']}: {g['detail']}\n")

            f.write("\nKẾT LUẬN\n")
            f.write(f"SAFE_TO_FIX_ACCOUNTS = {'YES' if safe else 'NO'}\n")
            f.write("- V4.2 KHÔNG thay đổi database.\n")

        zip_path = PROJECT_ROOT / (
            f"dry_run_7_tai_khoan_truong_nguon_QD3805_Nghi_Loc_v4_2_{ts}.zip"
        )
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 100)
        print("HOÀN THÀNH DRY-RUN V4.2")
        print("=" * 100)
        print(f"Tổng users nguồn: {len(moved_rows)}")
        print(f"Tài khoản Trường nguồn (truong_): {len(source_school_logins)}")
        print(f"CBQL (cbql.): {len(source_cbql)}")
        print(f"Giáo viên (gv.): {len(source_teachers)}")
        print(f"OTHER: {len(source_other)}")
        print(f"Bất thường: {len(anomalies)}")
        print(f"SAFE_TO_FIX_ACCOUNTS: {'YES' if safe else 'NO'}")
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
        print("=" * 100)
        print("ĐÃ DỪNG V4.2")
        print("=" * 100)
        print(str(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 100)
        print("LỖI SQLITE TRONG V4.2")
        print("=" * 100)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 100)
        print("LỖI KHÔNG DỰ KIẾN TRONG V4.2")
        print("=" * 100)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
