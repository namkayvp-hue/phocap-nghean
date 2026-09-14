from __future__ import annotations

import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import DATABASE_PATH
from app.permissions import is_admin_role, normalize_role_code

APP_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = APP_DIR.parent
EXPORT_DIR = PROJECT_DIR / "exports"

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter(
    prefix="/cong-cu-du-lieu",
    tags=["Công cụ dữ liệu"],
)

TARGET_YEAR_CODE = "2026-2027"
EXPECTED_BATCH_COUNT = 130
CONFIRM_PHRASE = "XOA DU LIEU THU 2026-2027"

BATCH_STATUS_LABELS = {
    "CHUAN_BI": "Chuẩn bị",
    "DANG_DIEU_TRA": "Đang điều tra",
    "DA_KET_THUC": "Đã kết thúc",
}


# === BAI_13B_10_V3_18B3_SAFE_QUERY_INT ===
def _safe_optional_int(value: Any) -> int | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if re.fullmatch(r"\d+", text):
        return int(text)

    return None

def _auth_user(request: Request) -> dict[str, Any]:
    return dict(request.scope.get("auth_user") or {})


def _admin_only(request: Request) -> bool:
    user = _auth_user(request)
    role_code = normalize_role_code(str(user.get("role_code") or ""))
    return is_admin_role(role_code) or role_code == "SO"


def _connect(*, read_only: bool) -> sqlite3.Connection:
    con = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30,
    )
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")

    if read_only:
        con.execute("PRAGMA query_only = ON")

    return con


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (name,),
    ).fetchone()
    return row is not None


def _all_tables(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def _columns(con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if not _table_exists(con, table):
        return []

    rows = con.execute(
        f"PRAGMA table_info({_quote_ident(table)})"
    ).fetchall()

    return [
        {
            "cid": int(row["cid"]),
            "name": str(row["name"]),
            "type": str(row["type"] or ""),
            "notnull": bool(row["notnull"]),
            "default": row["dflt_value"],
            "pk": int(row["pk"] or 0),
        }
        for row in rows
    ]


def _column_names(con: sqlite3.Connection, table: str) -> set[str]:
    return {item["name"] for item in _columns(con, table)}


def _simple_pk(con: sqlite3.Connection, table: str) -> str | None:
    pk_cols = sorted(
        (
            (item["pk"], item["name"])
            for item in _columns(con, table)
            if item["pk"]
        ),
        key=lambda x: x[0],
    )

    if len(pk_cols) != 1:
        return None

    return pk_cols[0][1]


def _foreign_keys(
    con: sqlite3.Connection,
    table: str,
) -> list[dict[str, str]]:
    if not _table_exists(con, table):
        return []

    rows = con.execute(
        f"PRAGMA foreign_key_list({_quote_ident(table)})"
    ).fetchall()

    result: list[dict[str, str]] = []
    for row in rows:
        result.append(
            {
                "parent_table": str(row["table"]),
                "from_col": str(row["from"]),
                "to_col": str(row["to"] or "id"),
            }
        )
    return result


def _scalar(
    con: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
) -> int:
    row = con.execute(sql, params).fetchone()
    if row is None:
        return 0
    return int(row[0] or 0)


def _chunks(values: list[int], size: int = 400):
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _select_ids_in(
    con: sqlite3.Connection,
    *,
    table: str,
    pk_col: str,
    filter_col: str,
    values: set[int],
) -> set[int]:
    result: set[int] = set()

    if not values:
        return result

    value_list = sorted(int(v) for v in values)

    for chunk in _chunks(value_list):
        placeholders = ",".join("?" for _ in chunk)
        sql = (
            f"SELECT {_quote_ident(pk_col)} "
            f"FROM {_quote_ident(table)} "
            f"WHERE {_quote_ident(filter_col)} IN ({placeholders})"
        )
        rows = con.execute(sql, tuple(chunk)).fetchall()

        for row in rows:
            if row[0] is not None:
                result.add(int(row[0]))

    return result


def _year_id(
    con: sqlite3.Connection,
    code: str,
) -> int | None:
    if not _table_exists(con, "school_years"):
        return None

    row = con.execute(
        """
        SELECT id
        FROM school_years
        WHERE code = ?
        LIMIT 1
        """,
        (code,),
    ).fetchone()

    return int(row[0]) if row else None


def _batch_ids_for_year(
    con: sqlite3.Connection,
    year_id: int,
) -> set[int]:
    if not _table_exists(con, "survey_batches"):
        return set()

    rows = con.execute(
        """
        SELECT id
        FROM survey_batches
        WHERE school_year_id = ?
        ORDER BY id
        """,
        (year_id,),
    ).fetchall()

    return {int(row[0]) for row in rows}


# === BAI_13B_10_V3_18B4_PROTECTED_DOMAINS ===
PROTECTED_EXACT_TABLES = {
    "communes",
    "schools",
    "users",
    "roles",
    "school_years",
    "students",
    "student_year_records",
    "student_school_year_records",
    "staff_members",
    "staff_year_records",
    "school_staff_year_summaries",
    "school_structured_report_inputs",
    "school_network_year_data",
    "school_network_year_datas",
}

PROTECTED_PREFIXES = (
    "staff_",
    "school_staff_",
    "school_structured_report_",
    "school_network_",
)


def _is_protected_domain_table(table: str) -> bool:
    name = str(table or "").strip().lower()

    if name in PROTECTED_EXACT_TABLES:
        return True

    return any(
        name.startswith(prefix)
        for prefix in PROTECTED_PREFIXES
    )


def _protected_target_tables(
    targets: dict[str, set[int]],
) -> list[str]:
    return sorted(
        table
        for table, ids in targets.items()
        if ids and _is_protected_domain_table(table)
    )


# === BAI_13B_10_V3_18B6_SCOPE_BY_COMMUNE ===
def _target_communes_for_year(
    con: sqlite3.Connection,
    *,
    year_code: str,
) -> list[dict[str, Any]]:
    year_id = _year_id(con, year_code)
    if year_id is None:
        return []

    rows = con.execute(
        '''
        SELECT
            c.id AS commune_id,
            c.code AS commune_code,
            c.name AS commune_name,
            sb.id AS batch_id,
            sb.code AS batch_code
        FROM survey_batches sb
        JOIN communes c
          ON c.id = sb.commune_id
        WHERE sb.school_year_id = ?
        ORDER BY c.name COLLATE NOCASE, c.code
        ''',
        (year_id,),
    ).fetchall()

    return [dict(row) for row in rows]


def _batch_ids_for_communes(
    con: sqlite3.Connection,
    *,
    year_code: str,
    commune_ids: set[int],
) -> set[int]:
    if not commune_ids:
        return set()

    year_id = _year_id(con, year_code)
    if year_id is None:
        return set()

    result: set[int] = set()
    values = sorted(int(v) for v in commune_ids)

    for chunk in _chunks(values):
        placeholders = ",".join("?" for _ in chunk)
        rows = con.execute(
            f'''
            SELECT id
            FROM survey_batches
            WHERE school_year_id = ?
              AND commune_id IN ({placeholders})
            ''',
            (year_id, *chunk),
        ).fetchall()

        result.update(
            int(row[0])
            for row in rows
            if row[0] is not None
        )

    return result


def _scope_from_form(
    con: sqlite3.Connection,
    *,
    scope_mode: str,
    selected_batch_id: str,
    commune_ids: list[str],
) -> dict[str, Any]:
    mode = str(scope_mode or "").strip().lower()

    year_id = _year_id(con, TARGET_YEAR_CODE)
    if year_id is None:
        raise RuntimeError(
            f"Không tìm thấy năm học {TARGET_YEAR_CODE}."
        )

    all_batch_ids = _batch_ids_for_year(con, year_id)

    if mode == "single":
        try:
            batch_id = int(str(selected_batch_id or "").strip())
        except Exception:
            raise RuntimeError(
                "Chưa chọn một xã/phường ở mục Kiểm tra từng đợt."
            )

        if batch_id not in all_batch_ids:
            raise RuntimeError(
                "Đợt được chọn không thuộc năm học 2026-2027."
            )

        row = con.execute(
            '''
            SELECT
                sb.id AS batch_id,
                c.id AS commune_id,
                c.code AS commune_code,
                c.name AS commune_name
            FROM survey_batches sb
            LEFT JOIN communes c ON c.id = sb.commune_id
            WHERE sb.id = ?
              AND sb.school_year_id = ?
            LIMIT 1
            ''',
            (batch_id, year_id),
        ).fetchone()

        if row is None:
            raise RuntimeError(
                "Không xác định được xã/phường của đợt đã chọn."
            )

        return {
            "mode": "single",
            "batch_ids": {batch_id},
            "commune_ids": (
                {int(row["commune_id"])}
                if row["commune_id"] is not None
                else set()
            ),
            "label": (
                "Chỉ "
                + str(row["commune_name"] or "xã/phường đã chọn")
            ),
            "count": 1,
        }

    if mode == "multi":
        parsed: set[int] = set()

        for raw in commune_ids or []:
            text = str(raw or "").strip()
            if text.isdigit():
                parsed.add(int(text))

        batch_ids = _batch_ids_for_communes(
            con,
            year_code=TARGET_YEAR_CODE,
            commune_ids=parsed,
        )

        if not batch_ids:
            raise RuntimeError(
                "Chưa chọn xã/phường nào trong chế độ Chọn nhiều xã."
            )

        return {
            "mode": "multi",
            "batch_ids": batch_ids,
            "commune_ids": parsed,
            "label": f"{len(batch_ids)} xã/phường đã chọn",
            "count": len(batch_ids),
        }

    if mode == "all":
        if len(all_batch_ids) != EXPECTED_BATCH_COUNT:
            raise RuntimeError(
                "Không thể chọn toàn bộ vì số đợt hiện tại "
                f"là {len(all_batch_ids)}, không phải "
                f"{EXPECTED_BATCH_COUNT}."
            )

        return {
            "mode": "all",
            "batch_ids": set(all_batch_ids),
            "commune_ids": set(),
            "label": f"Toàn bộ {EXPECTED_BATCH_COUNT} xã/phường",
            "count": len(all_batch_ids),
        }

    raise RuntimeError(
        "Phạm vi dọn không hợp lệ."
    )


def _count_preserved(con: sqlite3.Connection) -> dict[str, int]:
    result = {
        "communes": 0,
        "schools": 0,
        "users": 0,
        "students": 0,
        "staff": 0,
        "staff_year_records": 0,
        "structured_staff_forms": 0,
    }

    for table, key in (
        ("communes", "communes"),
        ("schools", "schools"),
        ("users", "users"),
        ("students", "students"),
        ("staff_members", "staff"),
        ("staff_year_records", "staff_year_records"),
    ):
        if _table_exists(con, table):
            result[key] = _scalar(
                con,
                f"SELECT COUNT(*) FROM {_quote_ident(table)}",
            )

    if _table_exists(con, "school_structured_report_inputs"):
        cols = _column_names(
            con,
            "school_structured_report_inputs",
        )
        if "form_code" in cols:
            result["structured_staff_forms"] = _scalar(
                con,
                '''
                SELECT COUNT(*)
                FROM school_structured_report_inputs
                WHERE UPPER(COALESCE(form_code, '')) IN (
                    'TH_01_GV',
                    'THCS_01_GV'
                )
                ''',
            )

    return result


def _seed_target_rows(
    con: sqlite3.Connection,
    batch_ids: set[int],
) -> dict[str, set[int]]:
    """
    Seed toàn bộ bảng nghiệp vụ có liên kết trực tiếp với survey_batches.
    Không bao giờ target survey_batches.
    """

    targets: dict[str, set[int]] = {}

    for table in _all_tables(con):
        if table == "survey_batches":
            continue

        pk = _simple_pk(con, table)
        if pk is None:
            continue

        cols = _column_names(con, table)

        direct_cols: set[str] = set()

        if (
            "survey_batch_id" in cols
            and (
                table.startswith("survey_")
                or table.startswith("student_survey_")
            )
        ):
            direct_cols.add("survey_batch_id")

        for fk in _foreign_keys(con, table):
            if (
                fk["parent_table"] == "survey_batches"
                and fk["to_col"] == "id"
            ):
                direct_cols.add(fk["from_col"])

        for direct_col in direct_cols:
            found = _select_ids_in(
                con,
                table=table,
                pk_col=pk,
                filter_col=direct_col,
                values=batch_ids,
            )
            if found:
                targets.setdefault(table, set()).update(found)

    return targets


def _private_and_shared_households(
    con: sqlite3.Connection,
    batch_ids: set[int],
) -> tuple[set[int], set[int], set[int]]:
    if (
        not batch_ids
        or not _table_exists(con, "survey_forms")
        or not _table_exists(con, "households")
    ):
        return set(), set(), set()

    values = sorted(batch_ids)
    placeholders = ",".join("?" for _ in values)

    target_households = {
        int(row[0])
        for row in con.execute(
            f"""
            SELECT DISTINCT household_id
            FROM survey_forms
            WHERE survey_batch_id IN ({placeholders})
            """,
            tuple(values),
        ).fetchall()
        if row[0] is not None
    }

    if not target_households:
        return set(), set(), set()

    private: set[int] = set()
    shared: set[int] = set()

    for household_id in sorted(target_households):
        remaining = _scalar(
            con,
            f"""
            SELECT COUNT(*)
            FROM survey_forms
            WHERE household_id = ?
              AND survey_batch_id NOT IN ({placeholders})
            """,
            (household_id, *values),
        )

        if remaining == 0:
            private.add(household_id)
        else:
            shared.add(household_id)

    return target_households, private, shared


def _propagate_children(
    con: sqlite3.Connection,
    targets: dict[str, set[int]],
) -> dict[str, set[int]]:
    """
    Đi từ parent đã target xuống toàn bộ child có FK.
    Nếu gặp child thực sự có dữ liệu target nhưng không có PK đơn,
    dừng an toàn thay vì tắt foreign_keys.
    """

    tables = _all_tables(con)

    changed = True
    while changed:
        changed = False

        for child in tables:
            if child == "survey_batches":
                continue

            child_pk = _simple_pk(con, child)

            for fk in _foreign_keys(con, child):
                parent = fk["parent_table"]
                parent_targets = targets.get(parent)

                if not parent_targets:
                    continue

                parent_pk = _simple_pk(con, parent)
                if (
                    parent_pk is None
                    or fk["to_col"] != parent_pk
                ):
                    continue

                if child_pk is None:
                    # Kiểm tra có row child trỏ vào target không.
                    hit = False
                    for chunk in _chunks(sorted(parent_targets)):
                        placeholders = ",".join("?" for _ in chunk)
                        row = con.execute(
                            f"""
                            SELECT 1
                            FROM {_quote_ident(child)}
                            WHERE {_quote_ident(fk["from_col"])}
                                  IN ({placeholders})
                            LIMIT 1
                            """,
                            tuple(chunk),
                        ).fetchone()
                        if row:
                            hit = True
                            break

                    if hit:
                        raise RuntimeError(
                            "Dừng an toàn: bảng "
                            f"{child} có dữ liệu phụ thuộc nhưng "
                            "không có khóa chính đơn để xóa có kiểm soát."
                        )
                    continue

                found = _select_ids_in(
                    con,
                    table=child,
                    pk_col=child_pk,
                    filter_col=fk["from_col"],
                    values=parent_targets,
                )

                if not found:
                    continue

                current = targets.setdefault(child, set())
                before = len(current)
                current.update(found)

                if len(current) > before:
                    changed = True

    return targets


def _build_delete_plan(
    con: sqlite3.Connection,
    *,
    year_code: str,
    batch_ids_override: set[int] | None = None,
) -> dict[str, Any]:
    year_id = _year_id(con, year_code)

    if year_id is None:
        raise RuntimeError(
            f"Không tìm thấy năm học {year_code}."
        )

    all_year_batch_ids = _batch_ids_for_year(con, year_id)

    if batch_ids_override is None:
        batch_ids = set(all_year_batch_ids)
    else:
        batch_ids = {
            int(batch_id)
            for batch_id in batch_ids_override
            if int(batch_id) in all_year_batch_ids
        }

    if not batch_ids:
        raise RuntimeError(
            "Phạm vi dọn không có đợt điều tra hợp lệ."
        )

    target_households, private_households, shared_households = (
        _private_and_shared_households(
            con,
            batch_ids,
        )
    )

    targets = _seed_target_rows(
        con,
        batch_ids,
    )

    # Giữ nguyên survey_batches, chỉ đưa các hộ riêng vào target.
    if private_households:
        targets.setdefault("households", set()).update(
            private_households
        )

    # Từ household riêng sẽ tự kéo survey_people và các child phụ thuộc.
    targets = _propagate_children(
        con,
        targets,
    )

    protected_targets = _protected_target_tables(targets)
    protection_ok = not protected_targets

    forms = len(targets.get("survey_forms", set()))
    people_private = len(targets.get("survey_people", set()))
    investigators = len(
        targets.get("survey_form_investigators", set())
    )
    teams = len(
        targets.get("survey_investigation_teams", set())
    )
    year_records = len(
        targets.get("survey_person_year_records", set())
    )
    assignment_logs = len(
        targets.get("survey_assignment_logs", set())
    )

    total_rows = sum(len(ids) for ids in targets.values())

    table_counts = [
        {
            "table": table,
            "count": len(ids),
        }
        for table, ids in sorted(
            targets.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
        if ids
    ]

    return {
        "year_id": year_id,
        "year_code": year_code,
        "batch_ids": sorted(batch_ids),
        "batch_count": len(batch_ids),
        "target_household_count": len(target_households),
        "private_household_ids": sorted(private_households),
        "private_household_count": len(private_households),
        "shared_household_ids": sorted(shared_households),
        "shared_household_count": len(shared_households),
        "forms": forms,
        "people_private": people_private,
        "year_records": year_records,
        "investigators": investigators,
        "teams": teams,
        "assignment_logs": assignment_logs,
        "total_rows": total_rows,
        "table_counts": table_counts,
        "targets": targets,
        "preserved": _count_preserved(con),
        "protected_target_tables": protected_targets,
        "protection_ok": protection_ok,
    }


def _delete_order(
    con: sqlite3.Connection,
    targets: dict[str, set[int]],
) -> list[str]:
    remaining = {
        table
        for table, ids in targets.items()
        if ids
    }

    edges: set[tuple[str, str]] = set()

    for child in remaining:
        for fk in _foreign_keys(con, child):
            parent = fk["parent_table"]

            if (
                parent in remaining
                and child != parent
            ):
                edges.add((child, parent))

    order: list[str] = []

    while remaining:
        leaves = sorted(
            table
            for table in remaining
            if not any(
                parent == table
                and child in remaining
                for child, parent in edges
            )
        )

        if not leaves:
            raise RuntimeError(
                "Dừng an toàn: phát hiện vòng phụ thuộc FK "
                "giữa các bảng cần dọn."
            )

        for table in leaves:
            order.append(table)
            remaining.remove(table)

    return order





# === BAI_13B_10_V3_21_BACKUP_MANAGER ===
BACKUP_DELETE_CONFIRM_PHRASE = "XOA BACKUP"


def _backup_manager_context(
    request: Request,
    *,
    manage_status: str = "",
    selected_backup_name: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    backups = _restore_backup_candidates()
    total_size_bytes = sum(
        int(item.get("size_bytes") or 0)
        for item in backups
    )
    newest_name = backups[0]["name"] if backups else ""

    return {
        "nguoi_dung": _auth_user(request),
        "backups": backups,
        "backup_count": len(backups),
        "total_size": _format_backup_size(total_size_bytes),
        "newest_backup_name": newest_name,
        "delete_confirm_phrase": BACKUP_DELETE_CONFIRM_PHRASE,
        "manage_status": manage_status,
        "selected_backup_name": selected_backup_name,
        "error_message": error_message,
    }


def _delete_system_backup(
    *,
    backup_name: str,
    actor: dict[str, Any],
) -> str:
    # Chỉ xóa một thư mục backup hợp lệ trong C:\PhoCap\exports.
    # Không bao giờ chạm DATABASE_PATH hiện tại.
    backups = _restore_backup_candidates()

    if len(backups) <= 1:
        raise RuntimeError(
            "Hệ thống phải giữ lại ít nhất 1 bản backup. "
            "Hãy tạo một bản Backup mới trước khi xóa."
        )

    newest_name = backups[0]["name"]
    if backup_name == newest_name:
        raise RuntimeError(
            "Bản backup mới nhất đang được bảo vệ. "
            "Chỉ xóa các bản cũ. Nếu thật sự cần loại bỏ bản này, "
            "hãy tạo một bản Backup mới trước."
        )

    backup_dir, db_path = _resolve_restore_backup(backup_name)

    if Path(DATABASE_PATH).resolve() == db_path.resolve():
        raise RuntimeError(
            "Dừng an toàn: đường dẫn backup trùng database hiện tại."
        )

    export_root = EXPORT_DIR.resolve()
    resolved_dir = backup_dir.resolve()

    if resolved_dir.parent != export_root:
        raise RuntimeError(
            "Dừng an toàn: thư mục cần xóa không nằm trực tiếp trong exports."
        )

    if backup_dir.is_symlink():
        raise RuntimeError(
            "Dừng an toàn: không cho phép xóa backup dạng liên kết."
        )

    deleted_name = backup_dir.name
    deleted_size = db_path.stat().st_size if db_path.exists() else 0

    shutil.rmtree(backup_dir)

    try:
        log_path = EXPORT_DIR / "nhat_ky_quan_ly_backup.jsonl"
        log_item = {
            "action": "delete_backup",
            "deleted_at": datetime.now().isoformat(),
            "backup_name": deleted_name,
            "database_size_bytes": int(deleted_size or 0),
            "actor": {
                "id": actor.get("id"),
                "username": actor.get("username"),
                "full_name": actor.get("full_name"),
                "role_code": actor.get("role_code"),
            },
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    log_item,
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass

    return deleted_name
# === BAI_13B_10_V3_20_DATABASE_RESTORE ===
RESTORE_CONFIRM_PHRASE = "KHOI PHUC DU LIEU"
RESTORE_BACKUP_PREFIXES = (
    "backup_thu_cong_",
    # === SAP_NHAP_TRUONG_DUNG_CHUNG_V9_2_BACKUP_PREFIX ===
    "backup_truoc_sap_nhap_",
    "backup_truoc_don_du_lieu_",
    "backup_truoc_khoi_phuc_",
)


def _format_backup_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{int(num_bytes or 0)} B"


def _restore_backup_type(name: str) -> str:
    if name.startswith("backup_thu_cong_"):
        return "Backup thủ công"
    # === SAP_NHAP_TRUONG_DUNG_CHUNG_V9_2_BACKUP_TYPE ===
    if name.startswith("backup_truoc_sap_nhap_"):
        return "Backup trước khi sáp nhập trường"
    if name.startswith("backup_truoc_don_du_lieu_"):
        return "Backup trước khi dọn dữ liệu"
    if name.startswith("backup_truoc_khoi_phuc_"):
        return "Backup an toàn trước lần khôi phục"
    return "Backup dữ liệu"


def _restore_backup_candidates() -> list[dict[str, Any]]:
    """Liệt kê các backup DB hợp lệ do hệ thống tạo trong exports."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    result: list[dict[str, Any]] = []

    for folder in EXPORT_DIR.iterdir():
        if not folder.is_dir():
            continue

        name = folder.name
        if not name.startswith(RESTORE_BACKUP_PREFIXES):
            continue

        db_path = folder / "phocap.db"
        if not db_path.is_file():
            continue

        try:
            stat = db_path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime)
        except OSError:
            continue

        result.append(
            {
                "name": name,
                "type": _restore_backup_type(name),
                "created_at": modified.strftime("%d/%m/%Y %H:%M:%S"),
                "size": _format_backup_size(stat.st_size),
                "size_bytes": int(stat.st_size),
                "mtime": float(stat.st_mtime),
                "path": str(db_path),
            }
        )

    result.sort(key=lambda item: item["mtime"], reverse=True)
    return result


def _resolve_restore_backup(backup_name: str) -> tuple[Path, Path]:
    name = str(backup_name or "").strip()
    if not name:
        raise RuntimeError("Bạn chưa chọn bản backup cần khôi phục.")

    if Path(name).name != name or "/" in name or "\\" in name:
        raise RuntimeError("Tên bản backup không hợp lệ.")

    if not name.startswith(RESTORE_BACKUP_PREFIXES):
        raise RuntimeError(
            "Bản backup không thuộc nhóm backup do hệ thống cho phép khôi phục."
        )

    backup_dir = EXPORT_DIR / name
    db_path = backup_dir / "phocap.db"

    if not backup_dir.is_dir() or not db_path.is_file():
        raise RuntimeError(
            "Không tìm thấy phocap.db trong bản backup đã chọn."
        )

    export_root = EXPORT_DIR.resolve()
    resolved_dir = backup_dir.resolve()
    if resolved_dir.parent != export_root:
        raise RuntimeError("Đường dẫn bản backup không hợp lệ.")

    return backup_dir, db_path


def _check_database_file(db_path: Path) -> dict[str, Any]:
    if not db_path.is_file():
        raise RuntimeError(f"Không tìm thấy database: {db_path}")

    con = sqlite3.connect(
        str(db_path),
        timeout=30,
    )
    try:
        integrity = con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if str(integrity).lower() != "ok":
            raise RuntimeError(
                f"Database không đạt integrity_check: {integrity}"
            )

        foreign_key_rows = con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if foreign_key_rows:
            raise RuntimeError(
                "Database có lỗi foreign_key_check; không cho phép khôi phục."
            )

        table_count = con.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchone()[0]
    finally:
        con.close()

    if int(table_count or 0) <= 0:
        raise RuntimeError(
            "Database backup không có bảng nghiệp vụ; dừng an toàn."
        )

    return {
        "integrity": str(integrity),
        "foreign_key_check": "ok",
        "table_count": int(table_count or 0),
        "size_bytes": db_path.stat().st_size,
    }


def _backup_before_restore(
    *,
    actor: dict[str, Any],
    selected_backup_name: str,
) -> Path:
    """Backup DB hiện tại trước khi ghi dữ liệu từ bản cũ vào."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = EXPORT_DIR / f"backup_truoc_khoi_phuc_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    db_target = backup_dir / "phocap.db"

    src = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30,
    )
    dst = sqlite3.connect(
        str(db_target),
        timeout=30,
    )

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

    check_info = _check_database_file(db_target)

    metadata = {
        "backup_type": "automatic_before_restore",
        "created_at": datetime.now().isoformat(),
        "selected_restore_backup": selected_backup_name,
        "database_source": str(DATABASE_PATH),
        "database_backup": str(db_target),
        "integrity_check": check_info["integrity"],
        "foreign_key_check": check_info["foreign_key_check"],
        "table_count": check_info["table_count"],
        "database_size_bytes": check_info["size_bytes"],
        "actor": {
            "id": actor.get("id"),
            "username": actor.get("username"),
            "full_name": actor.get("full_name"),
            "role_code": actor.get("role_code"),
        },
    }

    (backup_dir / "thong_tin_truoc_khoi_phuc.json").write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return backup_dir


def _copy_database_by_sqlite_backup(
    source_db: Path,
    target_db: Path,
) -> None:
    """Ghi toàn bộ source_db vào target_db bằng SQLite Backup API."""
    src = sqlite3.connect(
        str(source_db),
        timeout=30,
    )
    dst = sqlite3.connect(
        str(target_db),
        timeout=30,
    )

    try:
        dst.execute("PRAGMA busy_timeout = 30000")
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def _restore_page_context(
    request: Request,
    *,
    restore_status: str = "",
    selected_backup_name: str = "",
    safety_backup_name: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    return {
        "nguoi_dung": _auth_user(request),
        "backups": _restore_backup_candidates(),
        "restore_confirm_phrase": RESTORE_CONFIRM_PHRASE,
        "restore_status": restore_status,
        "selected_backup_name": selected_backup_name,
        "safety_backup_name": safety_backup_name,
        "error_message": error_message,
    }


def _perform_database_restore(
    *,
    actor: dict[str, Any],
    selected_backup_name: str,
) -> tuple[Path, dict[str, Any]]:
    """
    Kiểm tra backup -> backup DB hiện tại -> restore -> kiểm tra lại.
    Nếu restore lỗi sau khi đã chạm DB hiện tại, tự quay lại safety backup.
    """
    _, selected_db = _resolve_restore_backup(selected_backup_name)

    # Bắt buộc kiểm tra bản nguồn trước khi chạm database hiện tại.
    source_info = _check_database_file(selected_db)

    safety_dir = _backup_before_restore(
        actor=actor,
        selected_backup_name=selected_backup_name,
    )
    safety_db = safety_dir / "phocap.db"

    target_touched = False
    try:
        target_touched = True
        _copy_database_by_sqlite_backup(
            selected_db,
            Path(DATABASE_PATH),
        )

        restored_info = _check_database_file(
            Path(DATABASE_PATH)
        )

        log = {
            "restore_type": "full_database_restore",
            "restored_at": datetime.now().isoformat(),
            "selected_backup": selected_backup_name,
            "selected_database": str(selected_db),
            "safety_backup": safety_dir.name,
            "safety_database": str(safety_db),
            "source_check": source_info,
            "restored_check": restored_info,
            "actor": {
                "id": actor.get("id"),
                "username": actor.get("username"),
                "full_name": actor.get("full_name"),
                "role_code": actor.get("role_code"),
            },
        }

        (safety_dir / "nhat_ky_khoi_phuc.json").write_text(
            json.dumps(
                log,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return safety_dir, restored_info

    except Exception as restore_exc:
        rollback_error = None

        if target_touched and safety_db.is_file():
            try:
                _copy_database_by_sqlite_backup(
                    safety_db,
                    Path(DATABASE_PATH),
                )
                _check_database_file(
                    Path(DATABASE_PATH)
                )
            except Exception as rollback_exc:
                rollback_error = rollback_exc

        if rollback_error is None:
            raise RuntimeError(
                "Khôi phục không thành công. "
                "Hệ thống đã tự quay lại database trước khi khôi phục. "
                f"Chi tiết: {restore_exc}"
            ) from restore_exc

        raise RuntimeError(
            "KHẨN CẤP: Khôi phục lỗi và tự quay lại cũng lỗi. "
            f"Backup an toàn còn tại {safety_db}. "
            f"Lỗi restore: {restore_exc}; "
            f"lỗi rollback: {rollback_error}"
        ) from restore_exc


# === BAI_13B_10_V3_19_MANUAL_BACKUP ===
def _manual_backup_database(
    *,
    actor: dict[str, Any],
) -> Path:
    """Tạo bản sao đầy đủ phocap.db, không sửa/xóa dữ liệu hiện hành."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = EXPORT_DIR / f"backup_thu_cong_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    db_target = backup_dir / "phocap.db"

    src = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30,
    )
    dst = sqlite3.connect(str(db_target))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(str(db_target))
    try:
        integrity = check.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        table_count = check.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchone()[0]
    finally:
        check.close()

    if str(integrity).lower() != "ok":
        raise RuntimeError(
            "Backup thủ công không đạt integrity_check."
        )

    metadata = {
        "backup_type": "manual_full_database",
        "created_at": datetime.now().isoformat(),
        "database_source": str(DATABASE_PATH),
        "database_backup": str(db_target),
        "database_size_bytes": db_target.stat().st_size,
        "table_count": int(table_count or 0),
        "integrity_check": integrity,
        "actor": {
            "id": actor.get("id"),
            "username": actor.get("username"),
            "full_name": actor.get("full_name"),
            "role_code": actor.get("role_code"),
        },
    }

    (backup_dir / "thong_tin_backup.json").write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return backup_dir


def _backup_database(
    plan: dict[str, Any],
    *,
    actor: dict[str, Any],
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (
        EXPORT_DIR
        / f"backup_truoc_don_du_lieu_2026_2027_{stamp}"
    )
    backup_dir.mkdir(parents=True, exist_ok=False)

    db_target = backup_dir / "phocap.db"

    src = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30,
    )
    dst = sqlite3.connect(str(db_target))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(str(db_target))
    try:
        integrity = check.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    finally:
        check.close()

    if str(integrity).lower() != "ok":
        raise RuntimeError(
            "Backup database không đạt integrity_check."
        )

    serializable_plan = {
        key: value
        for key, value in plan.items()
        if key != "targets"
    }

    (backup_dir / "ke_hoach_truoc_khi_don.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(),
                "actor": {
                    "id": actor.get("id"),
                    "username": actor.get("username"),
                    "full_name": actor.get("full_name"),
                    "role_code": actor.get("role_code"),
                },
                "integrity_check": integrity,
                "plan": serializable_plan,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return backup_dir


def _delete_rows(
    con: sqlite3.Connection,
    *,
    table: str,
    pk_col: str,
    ids: set[int],
) -> int:
    if not ids:
        return 0

    deleted = 0
    for chunk in _chunks(sorted(ids)):
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"""
            DELETE FROM {_quote_ident(table)}
            WHERE {_quote_ident(pk_col)}
                  IN ({placeholders})
            """,
            tuple(chunk),
        )
        deleted += int(cursor.rowcount or 0)

    return deleted


def _execute_cleanup(
    *,
    plan: dict[str, Any],
    actor: dict[str, Any],
    backup_dir: Path,
) -> dict[str, Any]:
    con = _connect(read_only=False)

    result: dict[str, Any] = {
        "deleted_by_table": [],
        "deleted_total": 0,
        "backup_dir": str(backup_dir),
    }

    try:
        con.execute("BEGIN IMMEDIATE")

        # Rebuild plan trong chính transaction để tránh dữ liệu thay đổi
        # giữa lúc preview/backup và lúc xóa.
        live_plan = _build_delete_plan(
            con,
            year_code=TARGET_YEAR_CODE,
            batch_ids_override=set(plan["batch_ids"]),
        )

        if (
            set(live_plan["batch_ids"])
            != set(plan["batch_ids"])
        ):
            raise RuntimeError(
                "Phạm vi xã/phường đã thay đổi từ lúc tạo backup. "
                "Dừng an toàn."
            )

        # So sánh các chỉ tiêu cốt lõi với plan đã backup.
        for key in (
            "forms",
            "private_household_count",
            "shared_household_count",
            "total_rows",
        ):
            if live_plan[key] != plan[key]:
                raise RuntimeError(
                    "Dữ liệu đã thay đổi từ lúc tạo backup. "
                    f"Chỉ tiêu {key}: "
                    f"{plan[key]} -> {live_plan[key]}. "
                    "Dừng an toàn."
                )

        if not live_plan.get("protection_ok"):
            protected = ", ".join(
                live_plan.get("protected_target_tables") or []
            )
            raise RuntimeError(
                "VÙNG BẢO VỆ KHÔNG ĐẠT. "
                "Kế hoạch DELETE chạm bảng cần giữ: "
                + protected
            )

        targets = live_plan["targets"]
        order = _delete_order(
            con,
            targets,
        )

        for table in order:
            ids = targets.get(table, set())
            if not ids:
                continue

            pk = _simple_pk(con, table)
            if pk is None:
                raise RuntimeError(
                    f"Bảng {table} không có PK đơn."
                )

            deleted = _delete_rows(
                con,
                table=table,
                pk_col=pk,
                ids=ids,
            )

            result["deleted_by_table"].append(
                {
                    "table": table,
                    "count": deleted,
                }
            )
            result["deleted_total"] += deleted

        # Không UPDATE/DELETE survey_batches.
        remaining_forms = 0
        scoped_batch_ids = sorted(
            int(v) for v in plan["batch_ids"]
        )

        for chunk in _chunks(scoped_batch_ids):
            placeholders = ",".join("?" for _ in chunk)
            remaining_forms += _scalar(
                con,
                f"""
                SELECT COUNT(*)
                FROM survey_forms
                WHERE survey_batch_id
                      IN ({placeholders})
                """,
                tuple(chunk),
            )

        if remaining_forms != 0:
            raise RuntimeError(
                "Sau xóa trong transaction vẫn còn "
                f"{remaining_forms} phiếu trong phạm vi đã chọn."
            )
        batch_count_after = _scalar(
            con,
            """
            SELECT COUNT(*)
            FROM survey_batches sb
            JOIN school_years sy
              ON sy.id = sb.school_year_id
            WHERE sy.code = ?
            """,
            (TARGET_YEAR_CODE,),
        )

        if batch_count_after != EXPECTED_BATCH_COUNT:
            raise RuntimeError(
                "Số bản ghi survey_batches thay đổi ngoài ý muốn."
            )

        fk_errors = con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if fk_errors:
            raise RuntimeError(
                "foreign_key_check phát hiện lỗi sau khi dọn."
            )

        integrity = con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if str(integrity).lower() != "ok":
            raise RuntimeError(
                "integrity_check không đạt sau khi dọn."
            )

        con.commit()

        result["batch_count_after"] = batch_count_after
        result["remaining_forms"] = remaining_forms
        result["integrity_check"] = integrity
        result["preserved_after"] = _count_preserved(con)

        report_path = (
            backup_dir
            / "ket_qua_sau_khi_don.json"
        )
        report_path.write_text(
            json.dumps(
                {
                    "finished_at": datetime.now().isoformat(),
                    "actor": {
                        "id": actor.get("id"),
                        "username": actor.get("username"),
                        "full_name": actor.get("full_name"),
                        "role_code": actor.get("role_code"),
                    },
                    **result,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return result

    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _batch_options(
    con: sqlite3.Connection,
    school_year_id: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    years: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []

    if _table_exists(con, "school_years"):
        rows = con.execute(
            """
            SELECT id, code
            FROM school_years
            ORDER BY code DESC, id DESC
            """
        ).fetchall()
        years = [dict(row) for row in rows]

    if not _table_exists(con, "survey_batches"):
        return years, batches

    where = ""
    params: tuple[Any, ...] = ()

    if school_year_id:
        where = "WHERE sb.school_year_id = ?"
        params = (school_year_id,)

    rows = con.execute(
        f"""
        SELECT
            sb.id,
            sb.code,
            sb.name,
            sb.status,
            sb.school_year_id,
            sb.commune_id,
            sy.code AS school_year_code,
            c.code AS commune_code,
            c.name AS commune_name
        FROM survey_batches sb
        LEFT JOIN school_years sy
          ON sy.id = sb.school_year_id
        LEFT JOIN communes c
          ON c.id = sb.commune_id
        {where}
        ORDER BY
            COALESCE(sb.updated_at, sb.created_at) DESC,
            sb.id DESC
        """,
        params,
    ).fetchall()

    batches = [dict(row) for row in rows]
    return years, batches


def _selected_batch(
    con: sqlite3.Connection,
    batch_id: int,
) -> dict[str, Any] | None:
    row = con.execute(
        """
        SELECT
            sb.*,
            sy.code AS school_year_code,
            c.code AS commune_code,
            c.name AS commune_name
        FROM survey_batches sb
        LEFT JOIN school_years sy
          ON sy.id = sb.school_year_id
        LEFT JOIN communes c
          ON c.id = sb.commune_id
        WHERE sb.id = ?
        LIMIT 1
        """,
        (batch_id,),
    ).fetchone()

    return dict(row) if row else None


def _count_direct_batch(
    con: sqlite3.Connection,
    table: str,
    batch_id: int,
) -> int | None:
    cols = _column_names(con, table)
    if not cols or "survey_batch_id" not in cols:
        return None

    return _scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {_quote_ident(table)}
        WHERE survey_batch_id = ?
        """,
        (batch_id,),
    )


def _count_by_form(
    con: sqlite3.Connection,
    table: str,
    batch_id: int,
) -> int | None:
    cols = _column_names(con, table)
    if not cols or "survey_form_id" not in cols:
        return None

    return _scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {_quote_ident(table)} child
        JOIN survey_forms sf
          ON sf.id = child.survey_form_id
        WHERE sf.survey_batch_id = ?
        """,
        (batch_id,),
    )


def _inventory(
    con: sqlite3.Connection,
    batch_id: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rows": [],
        "summary": {
            "forms": 0,
            "households_linked": 0,
            "households_private": 0,
            "households_shared": 0,
            "people_linked": 0,
            "assignments": 0,
            "teams": 0,
        },
    }

    def add(
        label: str,
        value: int | None,
        group: str,
        note: str = "",
    ) -> None:
        result["rows"].append(
            {
                "label": label,
                "value": int(value or 0),
                "group": group,
                "note": note,
                "available": value is not None,
            }
        )

    forms = _scalar(
        con,
        """
        SELECT COUNT(*)
        FROM survey_forms
        WHERE survey_batch_id = ?
        """,
        (batch_id,),
    )
    add(
        "Phiếu điều tra",
        forms,
        "Dữ liệu lõi",
        "Phiếu thuộc đúng đợt đang xem.",
    )
    result["summary"]["forms"] = forms

    target_households, private, shared = (
        _private_and_shared_households(
            con,
            {batch_id},
        )
    )

    add(
        "Hộ dân liên kết với đợt",
        len(target_households),
        "Dữ liệu lõi",
    )
    add(
        "Hộ chỉ dùng riêng trong đợt này",
        len(private),
        "An toàn khi dọn",
    )
    add(
        "Hộ còn được dùng ở đợt khác",
        len(shared),
        "Phải giữ",
    )

    result["summary"]["households_linked"] = len(
        target_households
    )
    result["summary"]["households_private"] = len(private)
    result["summary"]["households_shared"] = len(shared)

    people = 0
    if target_households:
        values = sorted(target_households)
        for chunk in _chunks(values):
            placeholders = ",".join("?" for _ in chunk)
            people += _scalar(
                con,
                f"""
                SELECT COUNT(*)
                FROM survey_people
                WHERE household_id IN ({placeholders})
                """,
                tuple(chunk),
            )

    add(
        "Thành viên thuộc các hộ của đợt",
        people,
        "Dữ liệu lõi",
    )
    result["summary"]["people_linked"] = people

    year_records = _count_by_form(
        con,
        "survey_person_year_records",
        batch_id,
    )
    add(
        "Hồ sơ năm học",
        year_records,
        "Dữ liệu lõi",
    )

    investigators = _count_by_form(
        con,
        "survey_form_investigators",
        batch_id,
    )
    add(
        "Lượt phân công người điều tra",
        investigators,
        "Phân công",
    )
    result["summary"]["assignments"] = int(
        investigators or 0
    )

    logs = _count_by_form(
        con,
        "survey_assignment_logs",
        batch_id,
    )
    add(
        "Nhật ký giao / thay / thu hồi phiếu",
        logs,
        "Nhật ký",
    )

    teams = _count_direct_batch(
        con,
        "survey_investigation_teams",
        batch_id,
    )
    add(
        "Tổ điều tra 3 cấp",
        teams,
        "Tổ điều tra",
    )
    result["summary"]["teams"] = int(teams or 0)

    direct_tables = [
        (
            "survey_investigation_participants",
            "Giáo viên/CBQL trường gửi tham gia",
            "Phân công",
        ),
        (
            "survey_school_assignments",
            "Nhiệm vụ giao cho trường",
            "Phân công",
        ),
        (
            "survey_execution_workflow_logs",
            "Nhật ký luồng trường/xã",
            "Nhật ký",
        ),
        (
            "survey_file_exchange_logs",
            "Nhật ký giao nhận file",
            "Nhật ký",
        ),
        (
            "survey_household_import_jobs",
            "Lần nhập Excel hộ dân",
            "Nhập Excel",
        ),
    ]

    for table, label, group in direct_tables:
        add(
            label,
            _count_direct_batch(
                con,
                table,
                batch_id,
            ),
            group,
        )

    return result


def _cleanup_page_context(
    request: Request,
    *,
    school_year_id: int | None,
    batch_id: int | None,
    cleanup_status: str = "",
    backup_name: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    user = _auth_user(request)

    with _connect(read_only=True) as con:
        school_years, batches = _batch_options(
            con,
            school_year_id,
        )

        selected_batch = None
        inventory = None

        if batch_id:
            selected_batch = _selected_batch(
                con,
                int(batch_id),
            )
            if selected_batch is not None:
                inventory = _inventory(
                    con,
                    int(batch_id),
                )

        year_plan = _build_delete_plan(
            con,
            year_code=TARGET_YEAR_CODE,
        )

        target_communes = _target_communes_for_year(
            con,
            year_code=TARGET_YEAR_CODE,
        )

    year_plan_public = {
        key: value
        for key, value in year_plan.items()
        if key != "targets"
    }

    year_plan_public["safe_to_execute"] = (
        year_plan_public["batch_count"]
        == EXPECTED_BATCH_COUNT
        and year_plan_public.get("protection_ok") is True
    )

    return {
        "nguoi_dung": user,
        "school_years": school_years,
        "batches": batches,
        "selected_school_year_id": school_year_id,
        "selected_batch_id": batch_id,
        "selected_batch": selected_batch,
        "inventory": inventory,
        "status_labels": BATCH_STATUS_LABELS,
        "target_year_code": TARGET_YEAR_CODE,
        "expected_batch_count": EXPECTED_BATCH_COUNT,
        "confirm_phrase": CONFIRM_PHRASE,
        "year_plan": year_plan_public,
        "target_communes": target_communes,
        "cleanup_status": cleanup_status,
        "backup_name": backup_name,
        "error_message": error_message,
    }


@router.get(
    "/don-du-lieu-dieu-tra",
    response_class=HTMLResponse,
)
def survey_cleanup_preview(
    request: Request,
    school_year_id: str | None = Query(default=None),
    batch_id: str | None = Query(default=None),
    cleanup_status: str = Query(default=""),
    backup_name: str = Query(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    school_year_id_int = _safe_optional_int(school_year_id)
    batch_id_int = _safe_optional_int(batch_id)

    context = _cleanup_page_context(
        request,
        school_year_id=school_year_id_int,
        batch_id=batch_id_int,
        cleanup_status=cleanup_status,
        backup_name=backup_name,
    )

    return templates.TemplateResponse(
        request=request,
        name="data_tools/survey_cleanup.html",
        context=context,
    )





@router.get(
    "/don-du-lieu-dieu-tra/backup-quan-ly",
    response_class=HTMLResponse,
)
def database_backup_manager_page(
    request: Request,
    manage_status: str = Query(default=""),
    backup_name: str = Query(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="data_tools/database_backups.html",
        context=_backup_manager_context(
            request,
            manage_status=manage_status,
            selected_backup_name=backup_name,
        ),
    )


@router.post(
    "/don-du-lieu-dieu-tra/backup-quan-ly/xoa",
    response_class=HTMLResponse,
)
def delete_database_backup(
    request: Request,
    backup_name: str = Form(default=""),
    confirm_scope: str = Form(default=""),
    confirm_text: str = Form(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    if confirm_scope != "yes":
        return templates.TemplateResponse(
            request=request,
            name="data_tools/database_backups.html",
            context=_backup_manager_context(
                request,
                selected_backup_name=backup_name,
                error_message=(
                    "Bạn chưa đánh dấu xác nhận xóa bản backup đã chọn."
                ),
            ),
            status_code=400,
        )

    if confirm_text.strip().upper() != BACKUP_DELETE_CONFIRM_PHRASE:
        return templates.TemplateResponse(
            request=request,
            name="data_tools/database_backups.html",
            context=_backup_manager_context(
                request,
                selected_backup_name=backup_name,
                error_message=(
                    "Câu xác nhận chưa đúng. Hãy nhập chính xác: "
                    + BACKUP_DELETE_CONFIRM_PHRASE
                ),
            ),
            status_code=400,
        )

    actor = _auth_user(request)

    try:
        deleted_name = _delete_system_backup(
            backup_name=backup_name,
            actor=actor,
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request=request,
            name="data_tools/database_backups.html",
            context=_backup_manager_context(
                request,
                selected_backup_name=backup_name,
                error_message=(
                    "Không thể xóa bản backup. Chi tiết: "
                    + str(exc)
                ),
            ),
            status_code=400,
        )

    return RedirectResponse(
        url=(
            "/cong-cu-du-lieu/don-du-lieu-dieu-tra/backup-quan-ly"
            "?manage_status=deleted"
            f"&backup_name={deleted_name}"
        ),
        status_code=303,
    )
@router.get(
    "/don-du-lieu-dieu-tra/khoi-phuc",
    response_class=HTMLResponse,
)
def database_restore_page(
    request: Request,
    restore_status: str = Query(default=""),
    backup_name: str = Query(default=""),
    safety_name: str = Query(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    context = _restore_page_context(
        request,
        restore_status=restore_status,
        selected_backup_name=backup_name,
        safety_backup_name=safety_name,
    )

    return templates.TemplateResponse(
        request=request,
        name="data_tools/database_restore.html",
        context=context,
    )


@router.post(
    "/don-du-lieu-dieu-tra/khoi-phuc/thuc-hien",
    response_class=HTMLResponse,
)
def execute_database_restore(
    request: Request,
    backup_name: str = Form(default=""),
    confirm_scope: str = Form(default=""),
    confirm_text: str = Form(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    if confirm_scope != "yes":
        context = _restore_page_context(
            request,
            selected_backup_name=backup_name,
            error_message=(
                "Bạn chưa đánh dấu xác nhận đã kiểm tra đúng bản backup "
                "và đã dừng nhập liệu trước khi khôi phục."
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/database_restore.html",
            context=context,
            status_code=400,
        )

    if confirm_text.strip().upper() != RESTORE_CONFIRM_PHRASE:
        context = _restore_page_context(
            request,
            selected_backup_name=backup_name,
            error_message=(
                "Câu xác nhận chưa đúng. Hãy nhập chính xác: "
                + RESTORE_CONFIRM_PHRASE
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/database_restore.html",
            context=context,
            status_code=400,
        )

    actor = _auth_user(request)

    try:
        safety_dir, _ = _perform_database_restore(
            actor=actor,
            selected_backup_name=backup_name,
        )

        return RedirectResponse(
            url=(
                "/cong-cu-du-lieu/don-du-lieu-dieu-tra/khoi-phuc"
                "?restore_status=success"
                f"&backup_name={backup_name}"
                f"&safety_name={safety_dir.name}"
            ),
            status_code=303,
        )

    except Exception as exc:
        context = _restore_page_context(
            request,
            selected_backup_name=backup_name,
            error_message=(
                "Khôi phục dữ liệu KHÔNG thành công. Chi tiết: "
                + str(exc)
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/database_restore.html",
            context=context,
            status_code=500,
        )


@router.post(
    "/don-du-lieu-dieu-tra/backup",
    response_class=HTMLResponse,
)
def manual_survey_backup(
    request: Request,
):
    if not _admin_only(request):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    actor = _auth_user(request)

    try:
        backup_dir = _manual_backup_database(
            actor=actor,
        )

        return RedirectResponse(
            url=(
                "/cong-cu-du-lieu/don-du-lieu-dieu-tra"
                "?cleanup_status=backup_success"
                f"&backup_name={backup_dir.name}"
            ),
            status_code=303,
        )

    except Exception as exc:
        context = _cleanup_page_context(
            request,
            school_year_id=None,
            batch_id=None,
            error_message=(
                "Backup dữ liệu KHÔNG thành công. Chi tiết: "
                + str(exc)
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/survey_cleanup.html",
            context=context,
            status_code=500,
        )


@router.post(
    "/don-du-lieu-dieu-tra/thuc-hien",
    response_class=HTMLResponse,
)
def execute_survey_cleanup(
    request: Request,
    confirm_text: str = Form(default=""),
    confirm_scope: str = Form(default=""),
    scope_mode: str = Form(default="single"),
    selected_batch_id: str = Form(default=""),
    commune_ids: list[str] = Form(default=[]),
):
    if not _admin_only(request):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    # === BAI_13B_10_V3_18B6_SCOPE_BY_COMMUNE ===
    try:
        with _connect(read_only=True) as scope_con:
            selected_scope = _scope_from_form(
                scope_con,
                scope_mode=scope_mode,
                selected_batch_id=selected_batch_id,
                commune_ids=commune_ids,
            )
    except Exception as exc:
        context = _cleanup_page_context(
            request,
            school_year_id=None,
            batch_id=None,
            error_message=str(exc),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/survey_cleanup.html",
            context=context,
            status_code=400,
        )

    if confirm_scope != "yes":
        context = _cleanup_page_context(
            request,
            school_year_id=None,
            batch_id=None,
            error_message=(
                "Bạn chưa đánh dấu xác nhận phạm vi dọn "
                "toàn bộ dữ liệu thử nghiệm 2026-2027."
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/survey_cleanup.html",
            context=context,
            status_code=400,
        )

    if confirm_text.strip().upper() != CONFIRM_PHRASE:
        context = _cleanup_page_context(
            request,
            school_year_id=None,
            batch_id=None,
            error_message=(
                "Câu xác nhận chưa đúng. "
                f"Hãy nhập chính xác: {CONFIRM_PHRASE}"
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/survey_cleanup.html",
            context=context,
            status_code=400,
        )

    actor = _auth_user(request)

    try:
        with _connect(read_only=True) as con:
            plan = _build_delete_plan(
                con,
                year_code=TARGET_YEAR_CODE,
                batch_ids_override=set(
                    selected_scope["batch_ids"]
                ),
            )

        plan["scope_mode"] = selected_scope["mode"]
        plan["scope_label"] = selected_scope["label"]
        plan["scope_count"] = selected_scope["count"]

        backup_dir = _backup_database(
            plan,
            actor=actor,
        )

        result = _execute_cleanup(
            plan=plan,
            actor=actor,
            backup_dir=backup_dir,
        )

        return RedirectResponse(
            url=(
                "/cong-cu-du-lieu/don-du-lieu-dieu-tra"
                "?cleanup_status=success"
                f"&backup_name={backup_dir.name}"
            ),
            status_code=303,
        )

    except Exception as exc:
        context = _cleanup_page_context(
            request,
            school_year_id=None,
            batch_id=None,
            error_message=(
                "Dọn dữ liệu KHÔNG được thực hiện. "
                "Transaction đã rollback. Chi tiết: "
                + str(exc)
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/survey_cleanup.html",
            context=context,
            status_code=500,
        )
