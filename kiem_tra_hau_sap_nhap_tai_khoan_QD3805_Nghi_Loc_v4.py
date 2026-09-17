# -*- coding: utf-8 -*-
"""
DRY-RUN V4 - KIEM TRA TAI KHOAN HAU SAP NHAP QD 3805 - NGHI LOC
================================================================

MUC TIEU
--------
- CHI DOC database hien tai va BACKUP truoc sap nhap.
- KHONG SUA phocap.db.
- Doi chieu 152 users da chuyen bang ID tai khoan.
- Xac dinh tai khoan nao la cap TRUONG, GIAO VIEN, hay vai tro khac.
- Kiem tra moi truong dich da co tai khoan cap Truong "goc" truoc sap nhap hay chua.
- De xuat CHI o muc bao cao:
    + Tai khoan cap Truong cua truong nguon: khoa neu truong dich da co tai khoan cap Truong goc.
    + Tai khoan Giao vien: giu o truong dich.
- Phat hien trung/nhieu tai khoan cap Truong tren cung mot truong dich.
- Tao cong an toan SAFE_TO_FIX_ACCOUNTS de quyet dinh co the viet V5 hay chua.

KHONG DOI TEN TRUONG.
KHONG KHOA TAI KHOAN.
KHONG CAP NHAT DATABASE.

Chay PowerShell:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_hau_sap_nhap_tai_khoan_QD3805_Nghi_Loc_v4.py

Ket qua:
    C:\PhoCap\dry_run_hau_sap_nhap_tai_khoan_QD3805_Nghi_Loc_v4_<timestamp>.zip
"""

from __future__ import annotations

import csv
import re
import sqlite3
import sys
import unicodedata
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


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
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


def colset(conn: sqlite3.Connection, table: str) -> set[str]:
    return {c["name"] for c in columns(conn, table)}


def primary_key_column(conn: sqlite3.Connection, table: str) -> str:
    pks = [c for c in columns(conn, table) if c["pk"]]
    if len(pks) == 1:
        return pks[0]["name"]
    if "id" in colset(conn, table):
        return "id"
    raise AuditAbort("Bang users khong co khoa chinh don va khong co cot id.")


def first_existing(cols: set[str], candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        if c in cols:
            return c
    return None


def normalize_text(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def classify_role(raw_role) -> str:
    """
    Phan loai bao cao, KHONG dung de sua DB.
    Bao gom cac cach dat ten thuong gap cua du an.
    """
    r = normalize_text(raw_role)
    if not r:
        return "UNKNOWN"

    # Giao vien truoc de tranh chuoi role phuc hop.
    teacher_tokens = (
        "teacher", "giao_vien", "giaovien", "gv",
    )
    if r in teacher_tokens or any(tok in r for tok in ("teacher", "giao_vien", "giaovien")):
        return "TEACHER"

    commune_tokens = (
        "commune", "xa", "phuong", "commune_admin", "xa_admin",
    )
    if r in commune_tokens or "commune" in r or r.startswith("xa_"):
        return "COMMUNE"

    dept_tokens = (
        "department", "province", "so", "admin", "superadmin",
    )
    if r in dept_tokens or "department" in r or "province" in r or "superadmin" in r:
        return "DEPARTMENT_OR_ADMIN"

    school_tokens = (
        "school", "truong", "school_admin", "truong_admin",
        "school_account", "tai_khoan_truong",
    )
    if (
        r in school_tokens
        or "school" in r
        or "truong" in r
    ):
        return "SCHOOL"

    return "OTHER"


def find_backup() -> Path:
    candidates = sorted(
        BACKUP_DIR.glob("phocap_truoc_sap_nhap_QD3805_Nghi_Loc_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise AuditAbort(
            "Khong tim thay backup truoc sap nhap trong C:\\PhoCap\\backups."
        )
    return candidates[0]


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def school_names(conn: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(conn, "schools"):
        return {}
    cs = colset(conn, "schools")
    name_col = first_existing(cs, ("name", "school_name", "ten_truong"))
    if not name_col:
        return {}
    ids = sorted(set(SOURCE_IDS) | set(TARGET_IDS))
    rows = conn.execute(
        f"SELECT id, {qident(name_col)} FROM schools "
        f"WHERE id IN ({','.join('?' for _ in ids)})",
        ids,
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def school_states(conn: sqlite3.Connection) -> list[dict]:
    if not table_exists(conn, "schools"):
        return []
    cs = colset(conn, "schools")
    interesting = [
        c for c in (
            "id", "code", "name", "school_name", "ten_truong",
            "commune_id", "level", "school_level",
            "is_active", "active", "status"
        ) if c in cs
    ]
    if "id" not in interesting:
        interesting.insert(0, "id")
    ids = sorted(set(SOURCE_IDS) | set(TARGET_IDS))
    rows = conn.execute(
        "SELECT " + ", ".join(qident(c) for c in interesting)
        + f" FROM schools WHERE id IN ({','.join('?' for _ in ids)}) ORDER BY id",
        ids,
    ).fetchall()

    out = []
    for r in rows:
        d = {interesting[i]: r[i] for i in range(len(interesting))}
        sid = int(d["id"])
        d["merger_role"] = "SOURCE" if sid in MERGE_MAP else "TARGET"
        d["target_id_if_source"] = MERGE_MAP.get(sid, "")
        out.append(d)
    return out


def user_metadata(conn: sqlite3.Connection) -> dict:
    if not table_exists(conn, "users"):
        raise AuditAbort("Khong co bang users.")
    cs = colset(conn, "users")
    pk = primary_key_column(conn, "users")

    school_col = "school_id" if "school_id" in cs else None
    role_col = first_existing(cs, ("role", "role_name", "user_role", "account_role"))
    username_col = first_existing(cs, ("username", "user_name", "login_name", "login"))
    fullname_col = first_existing(
        cs, ("full_name", "fullname", "name", "display_name", "ho_ten")
    )
    active_col = first_existing(
        cs, ("is_active", "active", "enabled", "status", "is_locked", "locked")
    )
    commune_col = first_existing(cs, ("commune_id", "ward_id", "xa_id"))

    if not school_col:
        raise AuditAbort("Bang users khong co school_id.")
    if not role_col:
        raise AuditAbort(
            "Khong tim thay cot vai tro trong users "
            "(role/role_name/user_role/account_role)."
        )

    return {
        "pk": pk,
        "school_col": school_col,
        "role_col": role_col,
        "username_col": username_col,
        "fullname_col": fullname_col,
        "active_col": active_col,
        "commune_col": commune_col,
        "columns": sorted(cs),
    }


def fetch_users(conn: sqlite3.Connection, meta: dict) -> dict[int, dict]:
    cols = [meta["pk"], meta["school_col"], meta["role_col"]]
    for key in ("username_col", "fullname_col", "active_col", "commune_col"):
        c = meta[key]
        if c and c not in cols:
            cols.append(c)

    rows = conn.execute(
        "SELECT " + ", ".join(qident(c) for c in cols) + " FROM users"
    ).fetchall()

    result = {}
    for row in rows:
        d = {c: row[c] for c in cols}
        result[int(d[meta["pk"]])] = d
    return result


def value(d: dict | None, col: str | None):
    if not d or not col:
        return ""
    return d.get(col, "")


def is_probably_active(raw, active_col: str | None) -> str:
    """
    Chi danh dau de doc bao cao. Khong dung de sua.
    """
    if not active_col:
        return "UNKNOWN"
    name = normalize_text(active_col)
    v = raw
    if name in ("is_locked", "locked"):
        if v in (0, False, "0", "false", "False", None):
            return "YES"
        if v in (1, True, "1", "true", "True"):
            return "NO"
        return "UNKNOWN"
    if name in ("is_active", "active", "enabled"):
        if v in (1, True, "1", "true", "True"):
            return "YES"
        if v in (0, False, "0", "false", "False"):
            return "NO"
        return "UNKNOWN"

    # status dang chuoi
    s = normalize_text(v)
    if s in ("active", "enabled", "dang_hoat_dong", "hoat_dong"):
        return "YES"
    if s in ("inactive", "disabled", "locked", "khoa", "da_khoa"):
        return "NO"
    return "UNKNOWN"


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def audit() -> None:
    print("=" * 100)
    print("DRY-RUN V4 - KIEM TRA TAI KHOAN HAU SAP NHAP QD 3805 - NGHI LOC")
    print("=" * 100)
    print("Che do: CHI DOC - KHONG SUA DATABASE")

    if not CURRENT_DB.exists():
        raise AuditAbort(f"Khong tim thay database hien tai: {CURRENT_DB}")

    backup_db = find_backup()
    print(f"Current DB: {CURRENT_DB}")
    print(f"Backup DB : {backup_db}")

    cur = connect_ro(CURRENT_DB)
    bak = connect_ro(backup_db)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / f"dry_run_hau_sap_nhap_tai_khoan_QD3805_Nghi_Loc_v4_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        int_cur = cur.execute("PRAGMA integrity_check").fetchone()[0]
        int_bak = bak.execute("PRAGMA integrity_check").fetchone()[0]
        if int_cur != "ok":
            raise AuditAbort(f"Current DB integrity_check={int_cur}")
        if int_bak != "ok":
            raise AuditAbort(f"Backup DB integrity_check={int_bak}")

        meta_cur = user_metadata(cur)
        meta_bak = user_metadata(bak)

        # Phai cung khoa chinh/school/role de doi chieu an toan.
        for key in ("pk", "school_col", "role_col"):
            if meta_cur[key] != meta_bak[key]:
                raise AuditAbort(
                    f"Schema users current/backup khac nhau tai {key}: "
                    f"{meta_cur[key]} != {meta_bak[key]}"
                )

        users_cur = fetch_users(cur, meta_cur)
        users_bak = fetch_users(bak, meta_bak)

        names_cur = school_names(cur)
        names_bak = school_names(bak)

        moved = []
        anomalies = []

        # Tai khoan xuat phat tu 7 truong nguon trong backup.
        origin_source_ids = [
            uid for uid, u in users_bak.items()
            if u.get(meta_bak["school_col"]) in SOURCE_IDS
        ]

        for uid in sorted(origin_source_ids):
            b = users_bak[uid]
            c = users_cur.get(uid)
            source_id = int(b[meta_bak["school_col"]])
            expected_target = MERGE_MAP[source_id]

            if c is None:
                anomalies.append({
                    "type": "USER_MISSING_AFTER_MERGE",
                    "user_id": uid,
                    "source_school_id": source_id,
                    "expected_target_school_id": expected_target,
                    "detail": "Tai khoan co trong backup nhung khong con trong current DB",
                })
                continue

            current_school_id = c.get(meta_cur["school_col"])
            role_raw_before = b.get(meta_bak["role_col"])
            role_raw_after = c.get(meta_cur["role_col"])
            role_class = classify_role(role_raw_before)

            if current_school_id != expected_target:
                anomalies.append({
                    "type": "WRONG_TARGET_SCHOOL",
                    "user_id": uid,
                    "source_school_id": source_id,
                    "expected_target_school_id": expected_target,
                    "detail": f"current_school_id={current_school_id}",
                })

            if normalize_text(role_raw_before) != normalize_text(role_raw_after):
                anomalies.append({
                    "type": "ROLE_CHANGED_DURING_MERGE",
                    "user_id": uid,
                    "source_school_id": source_id,
                    "expected_target_school_id": expected_target,
                    "detail": f"before={role_raw_before}; after={role_raw_after}",
                })

            moved.append({
                "user_id": uid,
                "username": value(c, meta_cur["username_col"]) or value(b, meta_bak["username_col"]),
                "full_name_before": value(b, meta_bak["fullname_col"]),
                "full_name_after": value(c, meta_cur["fullname_col"]),
                "role_raw": role_raw_before,
                "role_class": role_class,
                "source_school_id": source_id,
                "source_school_name": names_bak.get(source_id, ""),
                "target_school_id": expected_target,
                "target_school_name": names_cur.get(expected_target, ""),
                "current_school_id": current_school_id,
                "active_raw_before": value(b, meta_bak["active_col"]),
                "active_raw_after": value(c, meta_cur["active_col"]),
                "probably_active_after": is_probably_active(
                    value(c, meta_cur["active_col"]), meta_cur["active_col"]
                ),
            })

        # Tai khoan cap Truong goc cua cac target: da thuoc target tu TRUOC sap nhap.
        native_target_school_accounts = defaultdict(list)
        all_target_school_accounts_current = defaultdict(list)

        for uid, b in users_bak.items():
            sid = b.get(meta_bak["school_col"])
            role_class = classify_role(b.get(meta_bak["role_col"]))
            if sid in TARGET_IDS and role_class == "SCHOOL":
                native_target_school_accounts[int(sid)].append(uid)

        for uid, c in users_cur.items():
            sid = c.get(meta_cur["school_col"])
            role_class = classify_role(c.get(meta_cur["role_col"]))
            if sid in TARGET_IDS and role_class == "SCHOOL":
                all_target_school_accounts_current[int(sid)].append(uid)

        moved_school_accounts = [
            r for r in moved if r["role_class"] == "SCHOOL"
        ]
        moved_teachers = [
            r for r in moved if r["role_class"] == "TEACHER"
        ]
        moved_other = [
            r for r in moved if r["role_class"] not in ("SCHOOL", "TEACHER")
        ]

        # De xuat tren tung tai khoan cap Truong cua source.
        recommendations = []
        for r in moved_school_accounts:
            target_id = int(r["target_school_id"])
            native_ids = sorted(native_target_school_accounts.get(target_id, []))
            current_school_ids = sorted(all_target_school_accounts_current.get(target_id, []))

            if len(native_ids) == 1:
                action = "LOCK_MOVED_SOURCE_SCHOOL_ACCOUNT"
                reason = (
                    "Truong dich da co dung 1 tai khoan cap Truong goc truoc sap nhap."
                )
            elif len(native_ids) == 0:
                action = "REVIEW_NO_NATIVE_TARGET_SCHOOL_ACCOUNT"
                reason = (
                    "Khong tim thay tai khoan cap Truong goc cua truong dich trong backup; "
                    "khong duoc khoa tu dong."
                )
            else:
                action = "REVIEW_MULTIPLE_NATIVE_TARGET_SCHOOL_ACCOUNTS"
                reason = (
                    f"Truong dich co {len(native_ids)} tai khoan cap Truong goc; "
                    "can xac minh tai khoan chinh."
                )

            recommendations.append({
                **r,
                "native_target_school_account_ids_before": ",".join(map(str, native_ids)),
                "school_account_ids_at_target_now": ",".join(map(str, current_school_ids)),
                "recommended_action": action,
                "reason": reason,
            })

        # Bang tong hop role theo source -> target.
        role_summary_counter = Counter()
        for r in moved:
            role_summary_counter[
                (
                    r["source_school_id"],
                    r["target_school_id"],
                    r["role_class"],
                    str(r["role_raw"]),
                )
            ] += 1

        role_summary = []
        for (source_id, target_id, role_class, role_raw), n in sorted(role_summary_counter.items()):
            role_summary.append({
                "source_school_id": source_id,
                "source_school_name": names_bak.get(source_id, ""),
                "target_school_id": target_id,
                "target_school_name": names_cur.get(target_id, ""),
                "role_class": role_class,
                "role_raw": role_raw,
                "count": n,
            })

        # Tong hop tai khoan SCHOOL tren moi target.
        target_account_summary = []
        for target_id in TARGET_IDS:
            native_ids = sorted(native_target_school_accounts.get(target_id, []))
            current_ids = sorted(all_target_school_accounts_current.get(target_id, []))
            moved_source_ids = sorted(
                int(r["user_id"]) for r in moved_school_accounts
                if int(r["target_school_id"]) == target_id
            )
            target_account_summary.append({
                "target_school_id": target_id,
                "target_school_name": names_cur.get(target_id, ""),
                "native_school_accounts_before_count": len(native_ids),
                "native_school_account_ids_before": ",".join(map(str, native_ids)),
                "moved_source_school_accounts_count": len(moved_source_ids),
                "moved_source_school_account_ids": ",".join(map(str, moved_source_ids)),
                "school_accounts_current_count": len(current_ids),
                "school_account_ids_current": ",".join(map(str, current_ids)),
            })

        # Gate an toan cho V5.
        unknown_roles = [r for r in moved if r["role_class"] in ("UNKNOWN", "OTHER")]
        school_reco_block = [
            r for r in recommendations
            if r["recommended_action"] != "LOCK_MOVED_SOURCE_SCHOOL_ACCOUNT"
        ]

        gate_checks = [
            {
                "check": "current_integrity_check",
                "result": "PASS" if int_cur == "ok" else "FAIL",
                "detail": str(int_cur),
            },
            {
                "check": "backup_integrity_check",
                "result": "PASS" if int_bak == "ok" else "FAIL",
                "detail": str(int_bak),
            },
            {
                "check": "moved_users_match_v1",
                "result": "PASS" if len(moved) == EXPECTED_MOVED_USERS else "FAIL",
                "detail": f"found={len(moved)}; expected={EXPECTED_MOVED_USERS}",
            },
            {
                "check": "no_user_merge_anomalies",
                "result": "PASS" if not anomalies else "FAIL",
                "detail": f"anomalies={len(anomalies)}",
            },
            {
                "check": "all_moved_roles_classified",
                "result": "PASS" if not unknown_roles else "FAIL",
                "detail": f"unknown_or_other={len(unknown_roles)}",
            },
            {
                "check": "all_source_school_accounts_have_single_native_target_account",
                "result": "PASS" if not school_reco_block else "FAIL",
                "detail": (
                    f"moved_school_accounts={len(moved_school_accounts)}; "
                    f"need_manual_review={len(school_reco_block)}"
                ),
            },
        ]

        safe = all(x["result"] == "PASS" for x in gate_checks)

        # CSV 30: schema users.
        schema_rows = []
        for c in columns(cur, "users"):
            schema_rows.append({
                "cid": c["cid"],
                "name": c["name"],
                "type": c["type"],
                "notnull": c["notnull"],
                "default": c["default"],
                "pk": c["pk"],
            })
        write_csv(
            out_dir / "30_SCHEMA_USERS.csv",
            ["cid", "name", "type", "notnull", "default", "pk"],
            schema_rows,
        )

        write_csv(
            out_dir / "31_152_TAI_KHOAN_DA_CHUYEN_CHI_TIET.csv",
            [
                "user_id", "username",
                "full_name_before", "full_name_after",
                "role_raw", "role_class",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "current_school_id",
                "active_raw_before", "active_raw_after",
                "probably_active_after",
            ],
            moved,
        )

        write_csv(
            out_dir / "32_TONG_HOP_VAI_TRO_THEO_TRUONG.csv",
            [
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "role_class", "role_raw", "count",
            ],
            role_summary,
        )

        write_csv(
            out_dir / "33_TAI_KHOAN_CAP_TRUONG_TAI_TRUONG_DICH.csv",
            [
                "target_school_id", "target_school_name",
                "native_school_accounts_before_count",
                "native_school_account_ids_before",
                "moved_source_school_accounts_count",
                "moved_source_school_account_ids",
                "school_accounts_current_count",
                "school_account_ids_current",
            ],
            target_account_summary,
        )

        write_csv(
            out_dir / "34_DE_XUAT_XU_LY_TAI_KHOAN_TRUONG_NGUON.csv",
            [
                "user_id", "username",
                "full_name_before", "full_name_after",
                "role_raw", "role_class",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "probably_active_after",
                "native_target_school_account_ids_before",
                "school_account_ids_at_target_now",
                "recommended_action", "reason",
            ],
            recommendations,
        )

        write_csv(
            out_dir / "35_BAT_THUONG_CAN_XEM.csv",
            [
                "type", "user_id", "source_school_id",
                "expected_target_school_id", "detail",
            ],
            anomalies,
        )

        write_csv(
            out_dir / "36_CONG_AN_TOAN_V5.csv",
            ["check", "result", "detail"],
            gate_checks,
        )

        school_rows = school_states(cur)
        headers = []
        for r in school_rows:
            for k in r:
                if k not in headers:
                    headers.append(k)
        if not headers:
            headers = ["id", "merger_role", "target_id_if_source"]
        write_csv(
            out_dir / "37_TRANG_THAI_TRUONG_HIEN_TAI.csv",
            headers,
            school_rows,
        )

        # Danh sach chi rieng teacher de kiem tra nhanh.
        write_csv(
            out_dir / "38_GIAO_VIEN_DA_CHUYEN.csv",
            [
                "user_id", "username", "full_name_after",
                "role_raw",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "probably_active_after",
            ],
            moved_teachers,
        )

        # OTHER/UNKNOWN.
        write_csv(
            out_dir / "39_VAI_TRO_KHAC_HOAC_CHUA_NHAN_DIEN.csv",
            [
                "user_id", "username", "full_name_after",
                "role_raw", "role_class",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
            ],
            moved_other,
        )

        summary = out_dir / "00_TONG_QUAN_V4.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write("DRY-RUN V4 - HAU SAP NHAP TAI KHOAN QD 3805 - NGHI LOC\n")
            f.write("=" * 100 + "\n")
            f.write("CHE DO: CHI DOC - KHONG SUA DATABASE\n")
            f.write(f"Current DB: {CURRENT_DB}\n")
            f.write(f"Backup DB : {backup_db}\n\n")

            f.write("1. DOI CHIEU 152 TAI KHOAN\n")
            f.write(f"- Tai khoan xuat phat tu 7 truong nguon: {len(moved)}\n")
            f.write(f"- SCHOOL: {len(moved_school_accounts)}\n")
            f.write(f"- TEACHER: {len(moved_teachers)}\n")
            f.write(f"- OTHER/UNKNOWN: {len(moved_other)}\n")
            f.write(f"- Bat thuong doi chieu ID/school/role: {len(anomalies)}\n\n")

            f.write("2. TAI KHOAN CAP TRUONG TAI CAC TRUONG DICH\n")
            for r in target_account_summary:
                f.write(
                    f"- {r['target_school_id']} {r['target_school_name']}: "
                    f"native_before={r['native_school_accounts_before_count']}; "
                    f"moved_source={r['moved_source_school_accounts_count']}; "
                    f"current_total={r['school_accounts_current_count']}\n"
                )

            f.write("\n3. DE XUAT DOI VOI TAI KHOAN CAP TRUONG NGUON\n")
            if not recommendations:
                f.write("- Khong tim thay tai khoan cap Truong trong 152 tai khoan da chuyen.\n")
            for r in recommendations:
                f.write(
                    f"- user_id={r['user_id']}; {r['username']}; "
                    f"{r['source_school_name']} -> {r['target_school_name']}; "
                    f"{r['recommended_action']}\n"
                )

            f.write("\n4. CONG AN TOAN\n")
            for g in gate_checks:
                f.write(f"- [{g['result']}] {g['check']}: {g['detail']}\n")

            f.write("\nKET LUAN\n")
            f.write(f"SAFE_TO_FIX_ACCOUNTS = {'YES' if safe else 'NO'}\n")
            if safe:
                f.write(
                    "- Du dieu kien ky thuat de viet V5 chi khoa cac tai khoan cap Truong "
                    "cua 7 truong nguon; KHONG khoa giao vien.\n"
                )
            else:
                f.write(
                    "- CHUA du dieu kien viet V5 tu dong. Can xem cac muc FAIL va CSV 35/39.\n"
                )
            f.write("- V4 KHONG thay doi database.\n")

        zip_path = PROJECT_ROOT / (
            f"dry_run_hau_sap_nhap_tai_khoan_QD3805_Nghi_Loc_v4_{ts}.zip"
        )
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 100)
        print("HOAN THANH DRY-RUN V4")
        print("=" * 100)
        print(f"Tai khoan doi chieu: {len(moved)} / expected {EXPECTED_MOVED_USERS}")
        print(f"  SCHOOL : {len(moved_school_accounts)}")
        print(f"  TEACHER: {len(moved_teachers)}")
        print(f"  OTHER/UNKNOWN: {len(moved_other)}")
        print(f"Bat thuong: {len(anomalies)}")
        print(f"SAFE_TO_FIX_ACCOUNTS: {'YES' if safe else 'NO'}")
        print(f"ZIP: {zip_path}")
        print("Khong co thay doi nao duoc ghi vao phocap.db.")

    finally:
        cur.close()
        bak.close()


def main() -> None:
    try:
        audit()
    except AuditAbort as e:
        print()
        print("=" * 100)
        print("DA DUNG DRY-RUN V4")
        print("=" * 100)
        print(str(e))
        print("Database KHONG bi thay doi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 100)
        print("LOI SQLITE TRONG DRY-RUN V4")
        print("=" * 100)
        print(repr(e))
        print("Database KHONG bi thay doi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 100)
        print("LOI KHONG DU KIEN TRONG DRY-RUN V4")
        print("=" * 100)
        print(repr(e))
        print("Database KHONG bi thay doi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
