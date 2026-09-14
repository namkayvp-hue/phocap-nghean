# -*- coding: utf-8 -*-
"""
DRY-RUN V4.1 - DO CẤU TRÚC USERS / VAI TRÒ HẬU SÁP NHẬP QD 3805 - NGHI LỘC
============================================================================

MỤC TIÊU
--------
- CHỈ ĐỌC database hiện tại và backup trước sáp nhập.
- KHÔNG SỬA phocap.db.
- Ghi ra:
  + Cấu trúc bảng users.
  + Foreign key của users.
  + Các cột có số lượng giá trị phân biệt thấp để nhận diện vai trò/trạng thái.
  + Các bảng có tên/cột liên quan role/quyen/permission/account/user.
  + 152 tài khoản xuất phát từ 7 trường nguồn, kèm toàn bộ cột an toàn để đối chiếu.
  + So sánh school_id trước/sau sáp nhập.
- KHÔNG tự suy đoán vai trò nếu chưa có căn cứ.

CHẠY:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_schema_users_hau_sap_nhap_QD3805_Nghi_Loc_v4_1.py

KẾT QUẢ:
    C:\PhoCap\dry_run_schema_users_QD3805_Nghi_Loc_v4_1_<timestamp>.zip
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import zipfile
from collections import Counter
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


def all_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def primary_key_column(conn: sqlite3.Connection, table: str) -> str:
    pks = [c for c in columns(conn, table) if c["pk"]]
    if len(pks) == 1:
        return pks[0]["name"]
    if "id" in colset(conn, table):
        return "id"
    raise AuditAbort(f"Không xác định được khóa chính đơn của bảng {table}.")


def foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA foreign_key_list({qident(table)})").fetchall()
    return [
        {
            "id": r[0],
            "seq": r[1],
            "ref_table": r[2],
            "from_col": r[3],
            "to_col": r[4] or "id",
            "on_update": r[5],
            "on_delete": r[6],
            "match": r[7] if len(r) > 7 else "",
        }
        for r in rows
    ]


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


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def school_names(conn: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(conn, "schools"):
        return {}
    cs = colset(conn, "schools")
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


def safe_distinct_values(conn: sqlite3.Connection, table: str, col: str, limit: int = 30):
    """
    Chỉ lấy distinct nếu <= limit+1 giá trị.
    Không dùng cho BLOB.
    """
    info = next((c for c in columns(conn, table) if c["name"] == col), None)
    if not info:
        return None
    typ = (info["type"] or "").upper()
    if "BLOB" in typ:
        return None

    try:
        cnt = conn.execute(
            f"SELECT COUNT(DISTINCT {qident(col)}) FROM {qident(table)}"
        ).fetchone()[0]
    except sqlite3.Error:
        return None

    if cnt is None or int(cnt) > limit:
        return None

    try:
        rows = conn.execute(
            f"SELECT {qident(col)}, COUNT(*) AS n "
            f"FROM {qident(table)} "
            f"GROUP BY {qident(col)} "
            f"ORDER BY n DESC, {qident(col)} "
            f"LIMIT {limit + 1}"
        ).fetchall()
        return [(r[0], int(r[1])) for r in rows]
    except sqlite3.Error:
        return None


def relevant_schema_tables(conn: sqlite3.Connection) -> list[dict]:
    keywords = (
        "role", "permission", "quyen", "user", "account",
        "teacher", "staff", "school", "auth"
    )
    out = []
    for table in all_tables(conn):
        t_low = table.lower()
        cs = columns(conn, table)
        col_names = [c["name"] for c in cs]
        hay = " ".join([t_low] + [x.lower() for x in col_names])
        if any(k in hay for k in keywords):
            out.append({
                "table": table,
                "columns": " | ".join(col_names),
                "foreign_keys": " | ".join(
                    f"{fk['from_col']}->{fk['ref_table']}.{fk['to_col']}"
                    for fk in foreign_keys(conn, table)
                ),
            })
    return out


def users_schema_report(conn: sqlite3.Connection) -> tuple[list[dict], list[dict], list[dict]]:
    if not table_exists(conn, "users"):
        raise AuditAbort("Không có bảng users.")

    schema = columns(conn, "users")
    fks = foreign_keys(conn, "users")

    distinct_rows = []
    for c in schema:
        vals = safe_distinct_values(conn, "users", c["name"], limit=30)
        if vals is None:
            continue
        for val, n in vals:
            distinct_rows.append({
                "column": c["name"],
                "type": c["type"],
                "value": "" if val is None else str(val),
                "count": n,
            })

    return schema, fks, distinct_rows


def fetch_source_users_full(
    conn: sqlite3.Connection,
    source_filter: bool,
) -> tuple[list[str], dict[int, dict]]:
    """
    Lấy toàn bộ cột users nhưng KHÔNG xuất các cột nhạy cảm rõ ràng như password/hash/token/secret.
    """
    cs = columns(conn, "users")
    all_cols = [c["name"] for c in cs]

    sensitive_tokens = (
        "password", "passwd", "pwd", "hash", "token", "secret",
        "salt", "otp", "refresh", "access_key", "api_key"
    )
    safe_cols = [
        c for c in all_cols
        if not any(tok in c.lower() for tok in sensitive_tokens)
    ]

    if "id" not in safe_cols and "id" in all_cols:
        safe_cols.insert(0, "id")
    if "school_id" not in safe_cols and "school_id" in all_cols:
        safe_cols.append("school_id")

    pk = primary_key_column(conn, "users")
    if pk not in safe_cols:
        safe_cols.insert(0, pk)

    sql = "SELECT " + ", ".join(qident(c) for c in safe_cols) + " FROM users"
    params = []
    if source_filter:
        if "school_id" not in all_cols:
            raise AuditAbort("Bảng users không có school_id.")
        marks = ",".join("?" for _ in SOURCE_IDS)
        sql += f" WHERE school_id IN ({marks})"
        params = list(SOURCE_IDS)

    rows = conn.execute(sql, params).fetchall()
    out = {}
    for r in rows:
        d = {c: r[c] for c in safe_cols}
        uid = int(d[pk])
        out[uid] = d

    return safe_cols, out


def build_comparison(
    backup_users: dict[int, dict],
    current_users: dict[int, dict],
    names_bak: dict[int, str],
    names_cur: dict[int, str],
) -> tuple[list[dict], list[dict]]:
    rows = []
    anomalies = []

    for uid in sorted(backup_users):
        b = backup_users[uid]
        c = current_users.get(uid)
        source_id = b.get("school_id")
        expected_target = MERGE_MAP.get(source_id)

        if c is None:
            anomalies.append({
                "user_id": uid,
                "type": "MISSING_AFTER_MERGE",
                "source_school_id": source_id,
                "expected_target_school_id": expected_target,
                "current_school_id": "",
                "detail": "Có trong backup nhưng không có trong current DB",
            })
            continue

        current_school = c.get("school_id")
        if current_school != expected_target:
            anomalies.append({
                "user_id": uid,
                "type": "WRONG_TARGET",
                "source_school_id": source_id,
                "expected_target_school_id": expected_target,
                "current_school_id": current_school,
                "detail": "school_id hiện tại không khớp MERGE_MAP",
            })

        # Các trường hiển thị thường gặp, chỉ dùng nếu có.
        def pick(d, names):
            for n in names:
                if n in d and d[n] not in (None, ""):
                    return d[n]
            return ""

        rows.append({
            "user_id": uid,
            "username": pick(c, ("username", "user_name", "login_name", "login")),
            "display_name_before": pick(
                b, ("full_name", "fullname", "display_name", "name", "ho_ten")
            ),
            "display_name_after": pick(
                c, ("full_name", "fullname", "display_name", "name", "ho_ten")
            ),
            "source_school_id": source_id,
            "source_school_name": names_bak.get(source_id, ""),
            "expected_target_school_id": expected_target,
            "expected_target_school_name": names_cur.get(expected_target, ""),
            "current_school_id": current_school,
            "school_move_ok": "YES" if current_school == expected_target else "NO",
        })

    return rows, anomalies


def audit() -> None:
    print("=" * 100)
    print("DRY-RUN V4.1 - DÒ CẤU TRÚC USERS / VAI TRÒ HẬU SÁP NHẬP QD 3805 - NGHI LỘC")
    print("=" * 100)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not CURRENT_DB.exists():
        raise AuditAbort(f"Không tìm thấy database hiện tại: {CURRENT_DB}")

    backup_db = find_backup()

    cur = connect_ro(CURRENT_DB)
    bak = connect_ro(backup_db)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / f"dry_run_schema_users_QD3805_Nghi_Loc_v4_1_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        int_cur = cur.execute("PRAGMA integrity_check").fetchone()[0]
        int_bak = bak.execute("PRAGMA integrity_check").fetchone()[0]

        if int_cur != "ok":
            raise AuditAbort(f"Current DB integrity_check={int_cur}")
        if int_bak != "ok":
            raise AuditAbort(f"Backup DB integrity_check={int_bak}")

        schema_cur, fks_cur, distinct_cur = users_schema_report(cur)
        schema_bak, fks_bak, distinct_bak = users_schema_report(bak)

        # 152 user gốc từ source trong BACKUP.
        safe_cols_bak, source_users_bak = fetch_source_users_full(bak, source_filter=True)

        # Toàn bộ current để đối chiếu đúng theo ID.
        safe_cols_cur, all_users_cur = fetch_source_users_full(cur, source_filter=False)

        names_bak = school_names(bak)
        names_cur = school_names(cur)

        comparison, anomalies = build_comparison(
            source_users_bak, all_users_cur, names_bak, names_cur
        )

        # Xuất toàn bộ 152 user trước/sau trên các cột an toàn chung.
        common_cols = [c for c in safe_cols_bak if c in safe_cols_cur]
        pk = primary_key_column(bak, "users")

        before_rows = []
        after_rows = []
        for uid in sorted(source_users_bak):
            b = source_users_bak[uid]
            before_rows.append({c: b.get(c, "") for c in common_cols})

            c = all_users_cur.get(uid, {})
            after_rows.append({cname: c.get(cname, "") for cname in common_cols})

        # Bảng schema liên quan role/quyền.
        relevant_cur = relevant_schema_tables(cur)
        relevant_bak = relevant_schema_tables(bak)

        # Tìm candidate role columns theo tên, không suy đoán dữ liệu.
        role_like_cols = []
        for c in schema_cur:
            n = c["name"].lower()
            if any(k in n for k in ("role", "quyen", "permission", "type", "scope", "level")):
                role_like_cols.append({
                    "column": c["name"],
                    "type": c["type"],
                    "reason": "Tên cột gợi ý vai trò/quyền/phạm vi",
                })

        # Tìm FK từ users tới bảng có tên role/quyen/permission.
        role_like_fks = []
        for fk in fks_cur:
            ref_low = fk["ref_table"].lower()
            from_low = fk["from_col"].lower()
            if any(k in ref_low or k in from_low for k in ("role", "quyen", "permission")):
                role_like_fks.append({
                    **fk,
                    "reason": "FK gợi ý quan hệ vai trò/quyền",
                })

        write_csv(
            out_dir / "40_USERS_SCHEMA_CURRENT.csv",
            ["cid", "name", "type", "notnull", "default", "pk"],
            schema_cur,
        )
        write_csv(
            out_dir / "41_USERS_FOREIGN_KEYS_CURRENT.csv",
            ["id", "seq", "ref_table", "from_col", "to_col", "on_update", "on_delete", "match"],
            fks_cur,
        )
        write_csv(
            out_dir / "42_USERS_DISTINCT_LOW_CARDINALITY_CURRENT.csv",
            ["column", "type", "value", "count"],
            distinct_cur,
        )
        write_csv(
            out_dir / "43_SCHEMA_BANG_LIEN_QUAN_USER_ROLE_PERMISSION.csv",
            ["table", "columns", "foreign_keys"],
            relevant_cur,
        )
        write_csv(
            out_dir / "44_COT_GOI_Y_VAI_TRO.csv",
            ["column", "type", "reason"],
            role_like_cols,
        )
        write_csv(
            out_dir / "45_FK_GOI_Y_VAI_TRO.csv",
            ["id", "seq", "ref_table", "from_col", "to_col", "on_update", "on_delete", "match", "reason"],
            role_like_fks,
        )
        write_csv(
            out_dir / "46_152_USERS_TRUOC_SAP_NHAP_AN_TOAN.csv",
            common_cols,
            before_rows,
        )
        write_csv(
            out_dir / "47_152_USERS_SAU_SAP_NHAP_AN_TOAN.csv",
            common_cols,
            after_rows,
        )
        write_csv(
            out_dir / "48_DOI_CHIEU_SCHOOL_ID_152_USERS.csv",
            [
                "user_id", "username",
                "display_name_before", "display_name_after",
                "source_school_id", "source_school_name",
                "expected_target_school_id", "expected_target_school_name",
                "current_school_id", "school_move_ok",
            ],
            comparison,
        )
        write_csv(
            out_dir / "49_BAT_THUONG_152_USERS.csv",
            [
                "user_id", "type", "source_school_id",
                "expected_target_school_id", "current_school_id", "detail",
            ],
            anomalies,
        )

        # Schema backup để phát hiện nếu đã thay đổi.
        write_csv(
            out_dir / "50_USERS_SCHEMA_BACKUP.csv",
            ["cid", "name", "type", "notnull", "default", "pk"],
            schema_bak,
        )
        write_csv(
            out_dir / "51_USERS_FOREIGN_KEYS_BACKUP.csv",
            ["id", "seq", "ref_table", "from_col", "to_col", "on_update", "on_delete", "match"],
            fks_bak,
        )

        summary = out_dir / "00_TONG_QUAN_V4_1.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write("DRY-RUN V4.1 - DÒ CẤU TRÚC USERS / VAI TRÒ HẬU SÁP NHẬP QD 3805\n")
            f.write("=" * 100 + "\n")
            f.write("CHẾ ĐỘ: CHỈ ĐỌC - KHÔNG SỬA DATABASE\n")
            f.write(f"Current DB: {CURRENT_DB}\n")
            f.write(f"Backup DB : {backup_db}\n")
            f.write(f"integrity current: {int_cur}\n")
            f.write(f"integrity backup : {int_bak}\n\n")

            f.write("1. ĐỐI CHIẾU 152 USERS\n")
            f.write(f"- Users xuất phát từ 7 trường nguồn trong backup: {len(source_users_bak)}\n")
            f.write(f"- Expected: {EXPECTED_MOVED_USERS}\n")
            f.write(f"- Bất thường school_id sau sáp nhập: {len(anomalies)}\n\n")

            f.write("2. USERS SCHEMA HIỆN TẠI\n")
            for c in schema_cur:
                f.write(
                    f"- {c['name']} | type={c['type']} | pk={c['pk']} | notnull={c['notnull']}\n"
                )

            f.write("\n3. FOREIGN KEY CỦA USERS\n")
            if not fks_cur:
                f.write("- Không có foreign key khai báo trong PRAGMA foreign_key_list(users).\n")
            else:
                for fk in fks_cur:
                    f.write(
                        f"- {fk['from_col']} -> {fk['ref_table']}.{fk['to_col']}\n"
                    )

            f.write("\n4. CỘT GỢI Ý VAI TRÒ/QUYỀN\n")
            if not role_like_cols:
                f.write("- Không có cột users nào có tên gợi ý role/quyen/permission/type/scope/level.\n")
            else:
                for r in role_like_cols:
                    f.write(f"- {r['column']} ({r['type']})\n")

            f.write("\n5. FK GỢI Ý VAI TRÒ/QUYỀN\n")
            if not role_like_fks:
                f.write("- Không phát hiện FK role/quyen/permission trực tiếp từ users.\n")
            else:
                for r in role_like_fks:
                    f.write(
                        f"- {r['from_col']} -> {r['ref_table']}.{r['to_col']}\n"
                    )

            f.write("\nKẾT LUẬN\n")
            if len(source_users_bak) == EXPECTED_MOVED_USERS and not anomalies:
                f.write("- 152/152 users vẫn khớp school_id sau sáp nhập.\n")
            else:
                f.write("- Cần xem 49_BAT_THUONG_152_USERS.csv.\n")
            f.write(
                "- V4.1 KHÔNG quyết định khóa tài khoản. "
                "Mục đích là xác định đúng schema vai trò trước khi viết V4.2/V5.\n"
            )
            f.write("- Database KHÔNG bị thay đổi.\n")

        zip_path = PROJECT_ROOT / (
            f"dry_run_schema_users_QD3805_Nghi_Loc_v4_1_{ts}.zip"
        )
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 100)
        print("HOÀN THÀNH DRY-RUN V4.1")
        print("=" * 100)
        print(f"Users nguồn tìm thấy trong backup: {len(source_users_bak)}")
        print(f"Bất thường school_id sau sáp nhập: {len(anomalies)}")
        print(f"Số cột users: {len(schema_cur)}")
        print(f"Số FK của users: {len(fks_cur)}")
        print(f"Cột gợi ý vai trò/quyền: {len(role_like_cols)}")
        print(f"FK gợi ý vai trò/quyền: {len(role_like_fks)}")
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
        print("ĐÃ DỪNG DRY-RUN V4.1")
        print("=" * 100)
        print(str(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 100)
        print("LỖI SQLITE TRONG V4.1")
        print("=" * 100)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 100)
        print("LỖI KHÔNG DỰ KIẾN TRONG V4.1")
        print("=" * 100)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
