from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database import DATABASE_PATH
from app.services import school_merger_service as engine
from app.services.school_merger_preview_service import (
    SchoolMergerPreviewError,
    build_official_plan_impact_preview,
)


OFFICIAL_CONFIRM_PHRASE = "SAP NHAP"
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
EXPORT_DIR = PROJECT_DIR / "exports"
OFFICIAL_EXECUTION_TABLE = "school_merger_official_executions"


class SchoolMergerExecutionError(RuntimeError):
    pass


def _safe_int(value: Any) -> int | None:
    try:
        text = str(value or "").strip()
        return int(text) if text else None
    except (TypeError, ValueError):
        return None


def _safe_folder_piece(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return text.strip("._-")[:70] or "plan"


def _source_ids_from_plan(plan: dict[str, Any]) -> list[int]:
    result: list[int] = []
    for item in plan.get("source_schools") or []:
        sid = _safe_int((item or {}).get("id"))
        if sid is not None and sid not in result:
            result.append(sid)
    return sorted(result)


def _exact_operation_map(con: sqlite3.Connection) -> dict[tuple[int, int, tuple[int, ...]], dict[str, Any]]:
    if not engine._table_exists(con, "school_merger_operations"):
        return {}
    rows = con.execute(
        "SELECT id,school_year_id,target_school_id,source_school_ids_json,"
        "actor_user_id,backup_name,summary_json,created_at "
        "FROM school_merger_operations ORDER BY id"
    ).fetchall()
    result: dict[tuple[int, int, tuple[int, ...]], dict[str, Any]] = {}
    for row in rows:
        try:
            source_ids = tuple(sorted(set(int(x) for x in json.loads(row["source_school_ids_json"] or "[]"))))
            key = (int(row["school_year_id"]), int(row["target_school_id"]), source_ids)
        except Exception:
            continue
        result[key] = dict(row)
    return result


def _official_execution_map(con: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    if not engine._table_exists(con, OFFICIAL_EXECUTION_TABLE):
        return {}
    rows = con.execute(
        f"SELECT id,plan_id,operation_id,school_year_id,target_school_id,"
        "source_school_ids_json,actor_user_id,actor_username,actor_full_name,"
        "backup_name,preview_fingerprint,summary_json,created_at "
        f"FROM {OFFICIAL_EXECUTION_TABLE} ORDER BY id"
    ).fetchall()
    return {str(row["plan_id"]): dict(row) for row in rows}


def annotate_official_plan_execution_status(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gắn trạng thái V4/V4.1 vào bản sao các phương án, không sửa sổ JSON chính thức."""
    copied = [dict(p) for p in plans]
    try:
        with engine._connect(read_only=True) as con:
            old_ops = _exact_operation_map(con)
            official_ops = _official_execution_map(con)
    except Exception:
        old_ops = {}
        official_ops = {}

    for plan in copied:
        action = str(plan.get("action_type") or "").upper()
        plan_id = str(plan.get("id") or "")
        if action == "KEEP":
            plan["execution_status"] = "NO_ACTION"
            plan["execution_label"] = "KHÔNG TÁC ĐỘNG"
            plan["execution_record"] = None
            continue

        year_id = _safe_int(plan.get("school_year_id"))
        target_id = _safe_int((plan.get("target_school") or {}).get("id"))
        source_ids = _source_ids_from_plan(plan)
        official = official_ops.get(plan_id)
        exact = None
        if year_id is not None and target_id is not None and source_ids:
            exact = old_ops.get((year_id, target_id, tuple(source_ids)))

        if official is not None:
            plan["execution_status"] = "COMPLETED"
            plan["execution_label"] = "ĐÃ SÁP NHẬP – V4/V4.1"
            plan["execution_record"] = official
        elif exact is not None:
            plan["execution_status"] = "COMPLETED_LEGACY"
            plan["execution_label"] = "ĐÃ THỰC HIỆN TRƯỚC V4"
            plan["execution_record"] = exact
        elif (
            action == "MAPPED"
            and str(plan.get("match_status") or "") == "MATCHED"
            and target_id is not None
            and bool(source_ids)
        ):
            plan["execution_status"] = "READY"
            plan["execution_label"] = "SẴN SÀNG XEM TRƯỚC"
            plan["execution_record"] = None
        else:
            plan["execution_status"] = "BLOCKED"
            plan["execution_label"] = "CHƯA ĐỦ ĐIỀU KIỆN"
            plan["execution_record"] = None
    return copied


def _ensure_audit_tables(con: sqlite3.Connection) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS school_merger_operations ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "school_year_id INTEGER NOT NULL,"
        "target_school_id INTEGER NOT NULL,"
        "source_school_ids_json TEXT NOT NULL,"
        "actor_user_id INTEGER,"
        "backup_name TEXT,"
        "summary_json TEXT NOT NULL,"
        "created_at DATETIME NOT NULL"
        ")"
    )
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {OFFICIAL_EXECUTION_TABLE} ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "plan_id TEXT NOT NULL UNIQUE,"
        "operation_id INTEGER,"
        "school_year_id INTEGER NOT NULL,"
        "target_school_id INTEGER NOT NULL,"
        "source_school_ids_json TEXT NOT NULL,"
        "actor_user_id INTEGER,"
        "actor_username TEXT,"
        "actor_full_name TEXT,"
        "backup_name TEXT NOT NULL,"
        "preview_fingerprint TEXT NOT NULL,"
        "summary_json TEXT NOT NULL,"
        "created_at DATETIME NOT NULL"
        ")"
    )


def _already_done_locked(
    con: sqlite3.Connection,
    *,
    plan_id: str,
    school_year_id: int,
    target_school_id: int,
    source_ids: list[int],
) -> dict[str, Any] | None:
    if engine._table_exists(con, OFFICIAL_EXECUTION_TABLE):
        row = con.execute(
            f"SELECT * FROM {OFFICIAL_EXECUTION_TABLE} WHERE plan_id=? LIMIT 1",
            (str(plan_id),),
        ).fetchone()
        if row is not None:
            return dict(row)

    if not engine._table_exists(con, "school_merger_operations"):
        return None
    rows = con.execute(
        "SELECT * FROM school_merger_operations "
        "WHERE school_year_id=? AND target_school_id=? ORDER BY id DESC",
        (int(school_year_id), int(target_school_id)),
    ).fetchall()
    wanted = sorted(set(int(x) for x in source_ids))
    for row in rows:
        try:
            got = sorted(set(int(x) for x in json.loads(row["source_school_ids_json"] or "[]")))
        except Exception:
            continue
        if got == wanted:
            return dict(row)
    return None


def _backup_locked_snapshot(
    *,
    plan_id: str,
    school_year_id: int,
    target_school_id: int,
    source_ids: list[int],
    actor: dict[str, Any],
) -> tuple[Path, str]:
    """Tạo backup khi transaction BEGIN IMMEDIATE đang giữ quyền ghi.

    Một kết nối đọc riêng được dùng để copy snapshot. Vì transaction thực hiện đã
    giữ write-reservation trước khi gọi hàm này, không writer khác có thể chen vào
    giữa bước kiểm tra dấu vân tay và bước backup.
    """
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    folder = EXPORT_DIR / f"backup_truoc_sap_nhap_v4_{stamp}_{_safe_folder_piece(plan_id)}"
    folder.mkdir(parents=True, exist_ok=False)
    db_target = folder / "phocap.db"

    src = engine._connect(read_only=True)
    dst = sqlite3.connect(str(db_target), timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    chk = sqlite3.connect(str(db_target), timeout=30)
    try:
        chk.row_factory = sqlite3.Row
        chk.execute("PRAGMA foreign_keys=ON")
        integrity = str(chk.execute("PRAGMA integrity_check").fetchone()[0])
        fk = chk.execute("PRAGMA foreign_key_check").fetchall()
        if integrity.lower() != "ok" or fk:
            raise SchoolMergerExecutionError(
                f"Backup trước sáp nhập không đạt kiểm tra: integrity={integrity}; fk={len(fk)}"
            )
    finally:
        chk.close()

    meta = {
        "backup_type": "automatic_before_official_school_merger_v4",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "plan_id": plan_id,
        "school_year_id": school_year_id,
        "target_school_id": target_school_id,
        "source_school_ids": source_ids,
        "actor": {
            "id": actor.get("id"),
            "username": actor.get("username"),
            "full_name": actor.get("full_name"),
            "role_code": actor.get("role_code"),
        },
        "database_backup": str(db_target),
        "status": "CREATED_BEFORE_TRANSACTION_MUTATION",
    }
    (folder / "thong_tin_sap_nhap_v4.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return folder, folder.name


def execute_official_plan(
    plan_id: str,
    *,
    actor: dict[str, Any],
    expected_impact_state_fingerprint: str,
    expected_source_audit_fingerprint: str,
    confirmation_scope: str,
    confirmation_text: str,
) -> dict[str, Any]:
    """Thực hiện đúng một phương án chính thức V4.3 trong một transaction duy nhất."""
    if str(confirmation_scope or "").strip().lower() != "yes":
        raise SchoolMergerExecutionError(
            "Bạn chưa đánh dấu xác nhận đã kiểm tra đúng trường nguồn, trường đích và năm hiệu lực."
        )
    if str(confirmation_text or "").strip().upper() != OFFICIAL_CONFIRM_PHRASE:
        raise SchoolMergerExecutionError(
            f"Câu xác nhận chưa đúng. Hãy nhập chính xác: {OFFICIAL_CONFIRM_PHRASE}"
        )
    if not str(expected_impact_state_fingerprint or "").strip():
        raise SchoolMergerExecutionError("Thiếu dấu vân tay dữ liệu tác động V4.1. Hãy XEM TRƯỚC TÁC ĐỘNG lại.")
    if not str(expected_source_audit_fingerprint or "").strip():
        raise SchoolMergerExecutionError("Thiếu dấu vân tay kiểm tra nguồn V4.3. Hãy XEM TRƯỚC TÁC ĐỘNG lại.")

    con = engine._connect(read_only=False)
    backup_dir: Path | None = None
    backup_name = ""
    committed = False
    preview: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    operation_id: int | None = None

    try:
        # Khóa quyền ghi TRƯỚC khi dựng lại preview. Nhờ vậy không writer nào có thể
        # thay đổi DB giữa kiểm tra fingerprint -> backup -> áp dụng -> hậu kiểm.
        con.execute("BEGIN IMMEDIATE")

        try:
            preview = build_official_plan_impact_preview(str(plan_id))
        except (SchoolMergerPreviewError, engine.SchoolMergerError, sqlite3.Error) as exc:
            raise SchoolMergerExecutionError(str(exc)) from exc

        if preview.get("keep_only"):
            raise SchoolMergerExecutionError("Phương án GIỮ NGUYÊN không có thao tác sáp nhập.")
        if not preview.get("safe_for_future_execution") or not preview.get("simulation_ok"):
            blockers = " | ".join(str(x) for x in (preview.get("blockers") or []))
            raise SchoolMergerExecutionError(
                "Phương án không còn đạt cổng an toàn. " + (blockers or "Hãy Xem trước lại.")
            )
        if not preview.get("v43_source_check_ok"):
            raise SchoolMergerExecutionError(
                "V4.3 đã chặn: dữ liệu nguồn chưa đạt kiểm tra bắt buộc. Hãy xem lại mục KIỂM TRA NGUỒN."
            )
        current_source_audit_fingerprint = str((preview.get("source_audit") or {}).get("fingerprint") or "")
        if not current_source_audit_fingerprint:
            raise SchoolMergerExecutionError(
                "Không dựng được dấu vân tay kiểm tra nguồn V4.3. Hãy XEM TRƯỚC TÁC ĐỘNG lại."
            )
        if str(expected_source_audit_fingerprint) != current_source_audit_fingerprint:
            raise SchoolMergerExecutionError(
                "Dữ liệu nguồn/đối chiếu V4.3 đã thay đổi kể từ lúc xem trước. "
                "Hệ thống đã chặn ghi database; hãy XEM TRƯỚC TÁC ĐỘNG lại."
            )
        current_impact_fingerprint = str(preview.get("impact_state_fingerprint") or "")
        if not current_impact_fingerprint:
            raise SchoolMergerExecutionError(
                "Không dựng được dấu vân tay dữ liệu tác động V4.1. Hãy XEM TRƯỚC TÁC ĐỘNG lại."
            )
        if str(expected_impact_state_fingerprint) != current_impact_fingerprint:
            raise SchoolMergerExecutionError(
                "Dữ liệu thuộc phạm vi sáp nhập đã thay đổi kể từ lúc xem trước. "
                "V4.1 đã chặn ghi database; hãy bấm XEM TRƯỚC TÁC ĐỘNG lại trước khi thực hiện."
            )

        year_id = _safe_int((preview.get("school_year") or {}).get("id"))
        target_id = _safe_int((preview.get("target_school") or {}).get("id"))
        source_ids = sorted(
            set(
                int(x["id"])
                for x in (preview.get("source_schools") or [])
                if _safe_int((x or {}).get("id")) is not None
            )
        )
        if year_id is None or target_id is None or not source_ids:
            raise SchoolMergerExecutionError("Không xác định đủ năm học / trường nguồn / trường đích.")

        if _already_done_locked(
            con,
            plan_id=str(plan_id),
            school_year_id=year_id,
            target_school_id=target_id,
            source_ids=source_ids,
        ) is not None:
            raise SchoolMergerExecutionError(
                "Phương án này đã có nhật ký sáp nhập. Không được thực hiện lần thứ hai."
            )

        backup_dir, backup_name = _backup_locked_snapshot(
            plan_id=str(plan_id),
            school_year_id=year_id,
            target_school_id=target_id,
            source_ids=source_ids,
            actor=actor,
        )

        previous_year_id = engine._previous_year_id(con, year_id)
        result = engine._apply_merge(
            con,
            selected_year_id=year_id,
            previous_year_id=previous_year_id,
            target_school_id=target_id,
            source_ids=source_ids,
            actor_user_id=_safe_int(actor.get("id")),
            backup_name=backup_name,
            record_audit=False,
        )

        result["official_plan_id"] = str(plan_id)
        result["preview_fingerprint"] = str(preview.get("fingerprint") or "")
        result["impact_state_fingerprint"] = str(preview.get("impact_state_fingerprint") or "")
        result["source_audit_fingerprint"] = str((preview.get("source_audit") or {}).get("fingerprint") or "")
        result["source_audit_status"] = str((preview.get("source_audit") or {}).get("status") or "")
        result["database_fingerprint"] = str(preview.get("database_fingerprint") or "")
        result["backup_name"] = backup_name
        result["source_school_names"] = [
            str(x.get("name") or x.get("excel_name") or "") for x in (preview.get("source_schools") or [])
        ]
        result["target_school_name"] = str(
            (preview.get("target_school") or {}).get("name")
            or (preview.get("target_school") or {}).get("excel_name")
            or ""
        )

        _ensure_audit_tables(con)
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        actor_id = _safe_int(actor.get("id"))
        summary_json = json.dumps(result, ensure_ascii=False, default=str)
        cur = con.execute(
            "INSERT INTO school_merger_operations ("
            "school_year_id,target_school_id,source_school_ids_json,actor_user_id,"
            "backup_name,summary_json,created_at) VALUES (?,?,?,?,?,?,?)",
            (
                year_id,
                target_id,
                json.dumps(source_ids, ensure_ascii=False),
                actor_id,
                backup_name,
                summary_json,
                now_text,
            ),
        )
        operation_id = int(cur.lastrowid)

        con.execute(
            f"INSERT INTO {OFFICIAL_EXECUTION_TABLE} ("
            "plan_id,operation_id,school_year_id,target_school_id,source_school_ids_json,"
            "actor_user_id,actor_username,actor_full_name,backup_name,preview_fingerprint,"
            "summary_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(plan_id),
                operation_id,
                year_id,
                target_id,
                json.dumps(source_ids, ensure_ascii=False),
                actor_id,
                str(actor.get("username") or ""),
                str(actor.get("full_name") or ""),
                backup_name,
                str(preview.get("fingerprint") or ""),
                summary_json,
                now_text,
            ),
        )

        # HẬU KIỂM nằm BÊN TRONG transaction, trước COMMIT. Nếu fail, rollback toàn bộ.
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        if fk or integrity.lower() != "ok":
            raise SchoolMergerExecutionError(
                f"Hậu kiểm trước COMMIT không đạt: integrity={integrity}; fk={len(fk)}"
            )

        con.commit()
        committed = True

    except Exception as exc:
        if not committed:
            try:
                con.rollback()
            except Exception:
                pass
        if backup_dir is not None:
            try:
                (backup_dir / "ket_qua_thu_thuc_hien_v4.json").write_text(
                    json.dumps(
                        {
                            "status": "ROLLED_BACK",
                            "plan_id": str(plan_id),
                            "error": str(exc),
                            "at": datetime.now().isoformat(timespec="seconds"),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass
        if isinstance(exc, SchoolMergerExecutionError):
            raise
        if isinstance(exc, engine.SchoolMergerError):
            raise SchoolMergerExecutionError(str(exc)) from exc
        if isinstance(exc, sqlite3.Error):
            raise SchoolMergerExecutionError("SQLite: " + str(exc)) from exc
        raise SchoolMergerExecutionError(str(exc)) from exc
    finally:
        con.close()

    assert preview is not None and result is not None and backup_dir is not None and operation_id is not None

    report_error = ""
    report_dir = EXPORT_DIR / (
        "sap_nhap_truong_v4_1_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        + "_" + _safe_folder_piece(plan_id)
    )
    try:
        report_dir.mkdir(parents=True, exist_ok=False)
        payload = {
            "status": "SUCCESS",
            "plan_id": str(plan_id),
            "operation_id": operation_id,
            "school_year": preview.get("school_year"),
            "target_school": preview.get("target_school"),
            "source_schools": preview.get("source_schools"),
            "backup_name": backup_name,
            "backup_dir": str(backup_dir),
            "actor": actor,
            "result": result,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "safety": {
                "single_transaction": True,
                "foreign_key_check_before_commit": "PASS",
                "integrity_check_before_commit": "PASS",
                "fingerprint_matched": True,
                "impact_state_fingerprint_matched_v41": True,
                "source_audit_fingerprint_matched_v43": True,
                "source_audit_pass_v43": True,
            },
        }
        (report_dir / "ket_qua_sap_nhap_v4_1.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        report_error = str(exc)

    return {
        "status": "SUCCESS",
        "plan_id": str(plan_id),
        "operation_id": operation_id,
        "backup_name": backup_name,
        "backup_dir": str(backup_dir),
        "report_dir": str(report_dir) if not report_error else "",
        "report_error": report_error,
        "preview": preview,
        "result": result,
    }


def get_official_execution_result(plan_id: str) -> dict[str, Any] | None:
    with engine._connect(read_only=True) as con:
        if not engine._table_exists(con, OFFICIAL_EXECUTION_TABLE):
            return None
        row = con.execute(
            f"SELECT * FROM {OFFICIAL_EXECUTION_TABLE} WHERE plan_id=? LIMIT 1",
            (str(plan_id),),
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["source_school_ids"] = [int(x) for x in json.loads(item.get("source_school_ids_json") or "[]")]
        except Exception:
            item["source_school_ids"] = []
        try:
            item["summary"] = json.loads(item.get("summary_json") or "{}")
        except Exception:
            item["summary"] = {}

        year = con.execute(
            "SELECT id,code,name FROM school_years WHERE id=? LIMIT 1",
            (int(item["school_year_id"]),),
        ).fetchone()
        target = con.execute(
            "SELECT id,code,name,commune_id,is_active FROM schools WHERE id=? LIMIT 1",
            (int(item["target_school_id"]),),
        ).fetchone()
        sources: list[dict[str, Any]] = []
        if item["source_school_ids"]:
            rows = con.execute(
                f"SELECT id,code,name,commune_id,is_active FROM schools "
                f"WHERE id IN ({engine._markers(len(item['source_school_ids']))}) ORDER BY name",
                item["source_school_ids"],
            ).fetchall()
            sources = [dict(x) for x in rows]

        item["school_year"] = dict(year) if year else None
        item["target_school"] = dict(target) if target else None
        item["source_schools"] = sources
        return item
