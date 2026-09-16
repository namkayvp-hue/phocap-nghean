from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.school_merger_official_registry import list_official_registry_plans
from app.services import school_merger_service as engine


class SchoolMergerSourceAuditError(RuntimeError):
    pass


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
SOURCE_ROSTER_DIR = PROJECT_DIR / "data" / "school_merger_source_rosters"
SOURCE_CORRECTION_FILE = PROJECT_DIR / "data" / "school_merger_source_corrections.json"
ACTIVE_SOURCE_LABELS = {"dang lam viec", "chuyen den"}
KNOWN_INACTIVE_TOKENS = (
    "nghi viec", "thoi viec", "nghi huu", "chuyen di", "da chuyen",
    "inactive", "resigned", "retired", "terminated",
)


def _normalize(value: Any) -> str:
    text = str(value or "").strip().lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    # Một số file nguồn cũ chứa chuỗi THamp;THCS do ký tự & bị encode hai lần.
    text = text.replace("thamp", "th ")
    text = re.sub(r"\bamp\b", " ", text)
    return " ".join(text.split())


def _bare_commune(value: Any) -> str:
    return re.sub(r"^(xa|phuong|thi tran|thi xa|thanh pho)\s+", "", _normalize(value))


def _school_key(value: Any) -> str:
    text = _normalize(value)
    text = re.sub(r"^truong\s+", "", text)
    text = re.sub(r"^th\s+", "tieu hoc ", text)
    return text


def _date_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return text


def _source_is_active(label: Any) -> bool:
    return _normalize(label) in ACTIVE_SOURCE_LABELS


def _db_row_is_inactive(row: sqlite3.Row | dict[str, Any]) -> bool:
    data = dict(row)
    if data.get("is_active") in (0, False, "0"):
        return True
    text = " ".join(
        _normalize(data.get(key))
        for key in ("status_code", "source_status_label", "notes")
        if data.get(key) not in (None, "")
    )
    return any(token in text for token in KNOWN_INACTIVE_TOKENS)


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _load_source_corrections() -> dict[str, Any]:
    """V4.4 – nạp các điều chỉnh nguồn có kiểm soát mà không sửa file Excel gốc.

    Mỗi điều chỉnh hiện hỗ trợ action=EXCLUDE_ROW và phải khóa đủ dataset_id + excel_row
    + staff_code. Nếu dòng nguồn không khớp đúng các khóa này, cổng dừng thay vì loại nhầm dữ liệu.
    """
    if not SOURCE_CORRECTION_FILE.exists():
        return {
            "version": 1,
            "corrections": [],
            "file": "",
            "sha256": "",
        }
    try:
        payload = json.loads(SOURCE_CORRECTION_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SchoolMergerSourceAuditError(
            f"Không đọc được sổ điều chỉnh nguồn {SOURCE_CORRECTION_FILE.name}: {exc}"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("corrections"), list):
        raise SchoolMergerSourceAuditError(
            f"Sổ điều chỉnh nguồn {SOURCE_CORRECTION_FILE.name} không đúng cấu trúc V4.4."
        )
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(payload.get("corrections") or [], start=1):
        if not isinstance(raw, dict):
            raise SchoolMergerSourceAuditError(f"Điều chỉnh nguồn #{index} không phải object JSON.")
        item = dict(raw)
        correction_id = str(item.get("correction_id") or "").strip()
        if not correction_id or correction_id in seen_ids:
            raise SchoolMergerSourceAuditError(
                f"Điều chỉnh nguồn #{index} thiếu correction_id hoặc bị trùng: {correction_id or '(rỗng)'}"
            )
        seen_ids.add(correction_id)
        action = str(item.get("action") or "").upper().strip()
        if action != "EXCLUDE_ROW":
            raise SchoolMergerSourceAuditError(
                f"Điều chỉnh {correction_id} dùng action chưa hỗ trợ: {action or '(rỗng)'}"
            )
        dataset_id = str(item.get("dataset_id") or "").strip()
        staff_code = str(item.get("staff_code") or "").strip()
        try:
            excel_row = int(item.get("excel_row"))
        except (TypeError, ValueError):
            excel_row = 0
        if not dataset_id or not staff_code or excel_row <= 0:
            raise SchoolMergerSourceAuditError(
                f"Điều chỉnh {correction_id} phải có dataset_id, staff_code và excel_row hợp lệ."
            )
        item["action"] = action
        item["dataset_id"] = dataset_id
        item["staff_code"] = staff_code
        item["excel_row"] = excel_row
        rows.append(item)
    return {
        "version": payload.get("version", 1),
        "corrections": rows,
        "file": SOURCE_CORRECTION_FILE.name,
        "sha256": _sha256_path(SOURCE_CORRECTION_FILE),
    }


@lru_cache(maxsize=1)
def _load_source_registry() -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    correction_registry = _load_source_corrections()
    corrections = list(correction_registry.get("corrections") or [])
    exclusions: dict[tuple[str, int], dict[str, Any]] = {}
    for item in corrections:
        key = (str(item.get("dataset_id") or ""), int(item.get("excel_row") or 0))
        if key in exclusions:
            raise SchoolMergerSourceAuditError(
                f"Nhiều điều chỉnh cùng nhắm tới {key[0]} / dòng Excel {key[1]}."
            )
        exclusions[key] = item
    applied_corrections: set[str] = set()

    if SOURCE_ROSTER_DIR.exists():
        for path in sorted(SOURCE_ROSTER_DIR.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise SchoolMergerSourceAuditError(f"Không đọc được nguồn đối chiếu {path.name}: {exc}") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
                raise SchoolMergerSourceAuditError(f"Nguồn đối chiếu {path.name} không đúng cấu trúc V4.3.")
            item = dict(payload)
            item["registry_file"] = path.name
            item["registry_sha256"] = _sha256_path(path)
            datasets.append(item)

    school_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    school_datasets: dict[tuple[str, str], set[str]] = defaultdict(set)
    # Xung đột mã nhân sự được xét trong CÙNG NĂM NGUỒN trên toàn các cấp đã đăng ký.
    # Không so chéo các năm khác nhau vì một người có thể chuyển trường hợp lệ qua các năm.
    code_rows_by_year: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    effective_row_counts: dict[str, int] = defaultdict(int)
    for dataset in datasets:
        dataset_id = str(dataset.get("dataset_id") or dataset.get("registry_file") or "")
        for raw in dataset.get("rows") or []:
            if not isinstance(raw, dict):
                continue
            try:
                raw_excel_row = int(raw.get("excel_row"))
            except (TypeError, ValueError):
                raw_excel_row = 0
            correction = exclusions.get((dataset_id, raw_excel_row))
            if correction is not None:
                source_code = str(raw.get("staff_code") or "").strip()
                if source_code != str(correction.get("staff_code") or "").strip():
                    raise SchoolMergerSourceAuditError(
                        f"Điều chỉnh {correction.get('correction_id')} không khớp staff_code tại "
                        f"{dataset_id} / dòng Excel {raw_excel_row}: nguồn={source_code}, "
                        f"điều chỉnh={correction.get('staff_code')}."
                    )
                expected_name = _normalize(correction.get("full_name"))
                if expected_name and _normalize(raw.get("full_name")) != expected_name:
                    raise SchoolMergerSourceAuditError(
                        f"Điều chỉnh {correction.get('correction_id')} không khớp họ tên tại "
                        f"dòng Excel {raw_excel_row}."
                    )
                expected_dob = _date_key(correction.get("date_of_birth"))
                if expected_dob and _date_key(raw.get("date_of_birth")) != expected_dob:
                    raise SchoolMergerSourceAuditError(
                        f"Điều chỉnh {correction.get('correction_id')} không khớp ngày sinh tại "
                        f"dòng Excel {raw_excel_row}."
                    )
                applied_corrections.add(str(correction.get("correction_id") or ""))
                continue
            row = dict(raw)
            effective_row_counts[dataset_id] += 1
            row["dataset_id"] = dataset_id
            row["level_code"] = str(dataset.get("level_code") or "").upper()
            row["school_year_code"] = str(dataset.get("school_year_code") or "")
            key = (_bare_commune(row.get("commune_name")), _school_key(row.get("school_name")))
            row["_school_key"] = key
            row["_active_source"] = _source_is_active(row.get("status_label"))
            school_rows[key].append(row)
            school_datasets[key].add(dataset_id)
            code = str(row.get("staff_code") or "").strip()
            if code:
                code_rows_by_year[(row["school_year_code"], code)].append(row)

    expected_correction_ids = {str(x.get("correction_id") or "") for x in corrections}
    if applied_corrections != expected_correction_ids:
        missing = sorted(expected_correction_ids - applied_corrections)
        extra = sorted(applied_corrections - expected_correction_ids)
        raise SchoolMergerSourceAuditError(
            "Sổ điều chỉnh nguồn không khớp registry hiện tại. "
            f"Chưa áp dụng được: {missing}; dư: {extra}."
        )

    duplicate_identity_codes: dict[tuple[str, str], list[dict[str, Any]]] = {}
    active_multi_school_codes: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for year_code_key, rows in code_rows_by_year.items():
        identities = {
            (_normalize(x.get("full_name")), _date_key(x.get("date_of_birth")))
            for x in rows
        }
        if len(identities) > 1:
            duplicate_identity_codes[year_code_key] = rows
        active = [x for x in rows if x.get("_active_source")]
        if len({tuple(x.get("_school_key") or ("", "")) for x in active}) > 1:
            active_multi_school_codes[year_code_key] = active

    dataset_summary = []
    for d in datasets:
        dataset_id = str(d.get("dataset_id") or d.get("registry_file") or "")
        raw_count = len(d.get("rows") or [])
        effective_count = int(effective_row_counts.get(dataset_id, 0))
        dataset_summary.append({
            "dataset_id": d.get("dataset_id"),
            "level_code": d.get("level_code"),
            "school_year_code": d.get("school_year_code"),
            "source_file": d.get("source_file"),
            "source_sha256": d.get("source_sha256"),
            "registry_file": d.get("registry_file"),
            "registry_sha256": d.get("registry_sha256"),
            "raw_row_count": raw_count,
            "row_count": effective_count,
            "excluded_row_count": raw_count - effective_count,
            "school_count": d.get("school_count"),
        })

    fingerprint_payload = {
        "datasets": dataset_summary,
        "correction_file": correction_registry.get("file"),
        "correction_sha256": correction_registry.get("sha256"),
        "correction_ids": sorted(applied_corrections),
        "duplicate_identity_codes": sorted(f"{year}|{code}" for year, code in duplicate_identity_codes),
        "active_multi_school_codes": sorted(f"{year}|{code}" for year, code in active_multi_school_codes),
    }
    registry_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()

    return {
        "datasets": datasets,
        "dataset_summary": dataset_summary,
        "school_rows": dict(school_rows),
        "school_datasets": {k: sorted(v) for k, v in school_datasets.items()},
        "duplicate_identity_codes": duplicate_identity_codes,
        "active_multi_school_codes": active_multi_school_codes,
        "correction_registry": correction_registry,
        "applied_correction_ids": sorted(applied_corrections),
        "registry_fingerprint": registry_fingerprint,
    }


def source_registry_summary() -> dict[str, Any]:
    reg = _load_source_registry()
    return {
        "dataset_count": len(reg["datasets"]),
        "datasets": reg["dataset_summary"],
        "school_roster_count": len(reg["school_rows"]),
        "duplicate_identity_code_count": len(reg["duplicate_identity_codes"]),
        "active_multi_school_code_count": len(reg["active_multi_school_codes"]),
        "correction_count": len(reg.get("applied_correction_ids") or []),
        "correction_ids": list(reg.get("applied_correction_ids") or []),
        "correction_file": (reg.get("correction_registry") or {}).get("file"),
        "correction_sha256": (reg.get("correction_registry") or {}).get("sha256"),
        "registry_fingerprint": reg["registry_fingerprint"],
    }


def _find_official_plan(plan_id: str) -> dict[str, Any]:
    wanted = str(plan_id or "").strip()
    if not wanted:
        raise SchoolMergerSourceAuditError("Thiếu mã phương án chính thức.")
    for plan in list_official_registry_plans(display_mode="all"):
        if str(plan.get("id") or "") == wanted:
            return plan
    raise SchoolMergerSourceAuditError(f"Không tìm thấy phương án chính thức: {wanted}")


def _school_year(con: sqlite3.Connection, year_id: int | None) -> dict[str, Any] | None:
    if year_id is None:
        return None
    row = con.execute("SELECT id,code,name FROM school_years WHERE id=? LIMIT 1", (int(year_id),)).fetchone()
    return dict(row) if row is not None else None


def _load_db_context(con: sqlite3.Connection, previous_year_id: int | None) -> dict[str, Any]:
    schools = [dict(r) for r in con.execute(
        "SELECT s.id,s.code,s.name,s.commune_id,s.is_active,c.name commune_name,c.code commune_code "
        "FROM schools s JOIN communes c ON c.id=s.commune_id"
    ).fetchall()]
    school_by_id = {int(x["id"]): x for x in schools}
    school_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for x in schools:
        school_by_key[(_bare_commune(x.get("commune_name")), _school_key(x.get("name")))].append(x)

    staff_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in con.execute(
        "SELECT id,ministry_staff_code,full_name,date_of_birth,is_active FROM staff_members "
        "WHERE ministry_staff_code IS NOT NULL AND TRIM(ministry_staff_code)<>''"
    ).fetchall():
        item = dict(row)
        staff_by_code[str(item.get("ministry_staff_code") or "").strip()].append(item)

    year_record_by_staff: dict[int, list[dict[str, Any]]] = defaultdict(list)
    year_record_count_by_school: dict[int, int] = defaultdict(int)
    if previous_year_id is not None and engine._table_exists(con, "staff_year_records"):
        rows = con.execute(
            "SELECT id,staff_member_id,school_year_id,school_id,status_code,is_active,source_status_label,notes "
            "FROM staff_year_records WHERE school_year_id=?",
            (int(previous_year_id),),
        ).fetchall()
        for row in rows:
            item = dict(row)
            year_record_by_staff[int(item["staff_member_id"])].append(item)
            year_record_count_by_school[int(item["school_id"])] += 1

    return {
        "schools": schools,
        "school_by_id": school_by_id,
        "school_by_key": dict(school_by_key),
        "staff_by_code": dict(staff_by_code),
        "year_record_by_staff": dict(year_record_by_staff),
        "year_record_count_by_school": dict(year_record_count_by_school),
    }


def _issue(code: str, message: str, *, staff_code: str = "", severity: str = "BLOCK", **extra: Any) -> dict[str, Any]:
    item = {"code": code, "message": message, "severity": severity}
    if staff_code:
        item["staff_code"] = staff_code
    item.update(extra)
    return item


def _audit_school(
    *,
    school: dict[str, Any],
    role: str,
    previous_year: dict[str, Any] | None,
    expected_level_code: str,
    registry: dict[str, Any],
    dbctx: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    warnings: list[str] = []
    school_id = int(school.get("id")) if school.get("id") is not None else None
    commune_name = str(school.get("commune_name") or school.get("commune_excel") or "")
    db_school = dbctx["school_by_id"].get(school_id) if school_id is not None else None
    if db_school is not None:
        commune_name = str(db_school.get("commune_name") or commune_name)
        school_name = str(db_school.get("name") or school.get("name") or school.get("excel_name") or "")
    else:
        school_name = str(school.get("name") or school.get("excel_name") or "")

    key = (_bare_commune(commune_name), _school_key(school_name))
    previous_year_code = str((previous_year or {}).get("code") or "")
    level_code = str(expected_level_code or "").upper().strip()
    roster_all = list(registry["school_rows"].get(key) or [])
    roster = [
        x for x in roster_all
        if str(x.get("level_code") or "").upper().strip() == level_code
        and str(x.get("school_year_code") or "") == previous_year_code
    ]
    if not roster:
        available = sorted({
            f"{x.get('level_code') or '?'} / {x.get('school_year_code') or '?'}"
            for x in roster_all
        })
        suffix = f" Nguồn cùng tên hiện có: {', '.join(available)}." if available else ""
        issues.append(_issue(
            "MISSING_SOURCE_ROSTER",
            f"Chưa có danh sách đội ngũ nguồn đúng cấp {level_code or '?'} / năm {previous_year_code or '?'} "
            f"để đối chiếu cho {school_name} – {commune_name}.{suffix}",
        ))
        return {
            "role": role,
            "status": "BLOCK",
            "school_id": school_id,
            "school_code": str((db_school or school).get("code") or ""),
            "school_name": school_name,
            "commune_name": commune_name,
            "source_roster_found": False,
            "source_total_rows": 0,
            "source_active_rows": 0,
            "db_previous_total_rows": int(dbctx["year_record_count_by_school"].get(school_id or -1, 0)),
            "active_identity_matched": 0,
            "active_at_expected_school": 0,
            "active_db_eligible": 0,
            "issues": issues,
            "warnings": warnings,
            "dataset_ids": [],
        }

    active = [x for x in roster if x.get("_active_source")]
    dataset_ids = sorted({str(x.get("dataset_id") or "") for x in roster if x.get("dataset_id")})
    active_identity_matched = 0
    active_at_expected_school = 0
    active_db_eligible = 0
    seen_issue_keys: set[tuple[Any, ...]] = set()

    def add_once(item: dict[str, Any]) -> None:
        key2 = (item.get("code"), item.get("staff_code"), item.get("message"))
        if key2 not in seen_issue_keys:
            seen_issue_keys.add(key2)
            issues.append(item)

    for row in active:
        code = str(row.get("staff_code") or "").strip()
        full_name = str(row.get("full_name") or "").strip()
        dob = _date_key(row.get("date_of_birth"))
        if not code:
            add_once(_issue("MISSING_STAFF_CODE", f"Dòng nguồn {row.get('excel_row')} – {full_name} thiếu mã định danh Bộ."))
            continue

        conflict_key = (previous_year_code, code)
        if conflict_key in registry["duplicate_identity_codes"]:
            examples = registry["duplicate_identity_codes"][conflict_key]
            names = sorted({str(x.get("full_name") or "") for x in examples})
            add_once(_issue(
                "DUPLICATE_CODE_DIFFERENT_IDENTITY",
                f"Mã {code} được dùng cho nhiều người khác nhau trong nguồn: {', '.join(names[:4])}.",
                staff_code=code,
            ))
        if conflict_key in registry["active_multi_school_codes"]:
            examples = registry["active_multi_school_codes"][conflict_key]
            schools = sorted({f"{x.get('commune_name')} / {x.get('school_name')}" for x in examples})
            add_once(_issue(
                "ACTIVE_IN_MULTIPLE_SOURCE_SCHOOLS",
                f"Mã {code} đang được ghi hoạt động ở nhiều trường trong cùng nguồn: {'; '.join(schools[:4])}.",
                staff_code=code,
            ))

        members = list(dbctx["staff_by_code"].get(code) or [])
        if len(members) != 1:
            add_once(_issue(
                "STAFF_CODE_DB_MATCH",
                f"Mã {code} trong database khớp {len(members)} hồ sơ staff_members; yêu cầu đúng 1.",
                staff_code=code,
            ))
            continue
        member = members[0]
        if _normalize(member.get("full_name")) != _normalize(full_name) or (
            dob and _date_key(member.get("date_of_birth")) and _date_key(member.get("date_of_birth")) != dob
        ):
            add_once(_issue(
                "STAFF_IDENTITY_MISMATCH",
                f"Mã {code} không khớp nhân thân nguồn: '{full_name}' {dob} / DB '{member.get('full_name')}' {_date_key(member.get('date_of_birth'))}.",
                staff_code=code,
            ))
            continue
        active_identity_matched += 1

        year_rows = list(dbctx["year_record_by_staff"].get(int(member["id"])) or [])
        if len(year_rows) != 1:
            add_once(_issue(
                "STAFF_YEAR_RECORD_COUNT",
                f"Mã {code} có {len(year_rows)} hồ sơ trong năm nguồn {str((previous_year or {}).get('code') or '')}; yêu cầu đúng 1.",
                staff_code=code,
            ))
            continue
        yr = year_rows[0]
        if school_id is None or int(yr.get("school_id") or -1) != int(school_id):
            actual = dbctx["school_by_id"].get(int(yr.get("school_id") or -1)) or {}
            add_once(_issue(
                "ACTIVE_STAFF_AT_WRONG_SCHOOL",
                f"Mã {code} – {full_name} theo nguồn thuộc {school_name}, nhưng DB năm nguồn đang ở '{actual.get('name') or yr.get('school_id')}'.",
                staff_code=code,
            ))
            continue
        active_at_expected_school += 1

        if _db_row_is_inactive(yr):
            add_once(_issue(
                "SOURCE_ACTIVE_BUT_DB_INACTIVE",
                f"Mã {code} – {full_name} là '{row.get('status_label')}' trong file nguồn nhưng DB đang phân loại không hoạt động ({yr.get('status_code')} / {yr.get('source_status_label') or ''}).",
                staff_code=code,
            ))
            continue
        active_db_eligible += 1

    db_previous_total = int(dbctx["year_record_count_by_school"].get(school_id or -1, 0))
    if db_previous_total != len(roster):
        warnings.append(
            f"Tổng dòng năm nguồn trong DB là {db_previous_total}, file nguồn có {len(roster)} dòng. "
            "Chênh lệch tổng lịch sử không tự động chặn vì một số người có thể đã chuyển đi; cổng cứng dùng danh sách đang hoạt động/chuyển đến."
        )

    expected_active = len(active)
    if active_db_eligible != expected_active:
        add_once(_issue(
            "ACTIVE_COUNT_MISMATCH",
            f"Đội ngũ hoạt động theo nguồn: {expected_active}; DB đủ điều kiện rollover tại đúng trường: {active_db_eligible}.",
        ))

    return {
        "role": role,
        "status": "PASS" if not issues else "BLOCK",
        "school_id": school_id,
        "school_code": str((db_school or school).get("code") or ""),
        "school_name": school_name,
        "commune_name": commune_name,
        "source_roster_found": True,
        "source_total_rows": len(roster),
        "source_active_rows": expected_active,
        "db_previous_total_rows": db_previous_total,
        "active_identity_matched": active_identity_matched,
        "active_at_expected_school": active_at_expected_school,
        "active_db_eligible": active_db_eligible,
        "issues": issues,
        "warnings": warnings,
        "dataset_ids": dataset_ids,
    }


def _audit_fingerprint(payload: dict[str, Any]) -> str:
    stable = {
        "plan_id": payload.get("plan_id"),
        "status": payload.get("status"),
        "previous_year": payload.get("previous_year"),
        "registry_fingerprint": payload.get("registry_fingerprint"),
        "school_checks": [
            {
                "role": x.get("role"),
                "status": x.get("status"),
                "school_id": x.get("school_id"),
                "school_code": x.get("school_code"),
                "source_total_rows": x.get("source_total_rows"),
                "source_active_rows": x.get("source_active_rows"),
                "db_previous_total_rows": x.get("db_previous_total_rows"),
                "active_identity_matched": x.get("active_identity_matched"),
                "active_at_expected_school": x.get("active_at_expected_school"),
                "active_db_eligible": x.get("active_db_eligible"),
                "issues": x.get("issues"),
                "dataset_ids": x.get("dataset_ids"),
            }
            for x in payload.get("school_checks") or []
        ],
    }
    return hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def audit_official_plan_source(
    plan_id: str,
    *,
    con: sqlite3.Connection | None = None,
    plan: dict[str, Any] | None = None,
    previous_year_id: int | None = None,
    _registry: dict[str, Any] | None = None,
    _dbctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """V4.3 – đối chiếu nguồn bắt buộc trước sáp nhập.

    Cổng cứng kiểm tra từng trường nguồn VÀ trường đích theo file nguồn đã đăng ký:
    địa bàn + tên trường + mã trường DB, danh sách nhân sự đang hoạt động/chuyển đến,
    mã định danh, nhân thân và vị trí hồ sơ năm liền trước trong database.
    """
    own_connection = con is None
    if plan is None:
        plan = _find_official_plan(plan_id)
    registry = _registry or _load_source_registry()

    if str(plan.get("action_type") or "").upper() == "KEEP":
        result = {
            "plan_id": str(plan.get("id") or plan_id),
            "status": "NOT_APPLICABLE",
            "pass": True,
            "message": "Phương án GIỮ NGUYÊN không cần cổng dữ liệu nguồn V4.3.",
            "previous_year": None,
            "school_checks": [],
            "blockers": [],
            "warnings": [],
            "registry_fingerprint": registry["registry_fingerprint"],
            "registry_summary": source_registry_summary(),
        }
        result["fingerprint"] = _audit_fingerprint(result)
        return result

    if own_connection:
        con = engine._connect(read_only=True)
    assert con is not None
    try:
        selected_year_id = plan.get("school_year_id")
        try:
            selected_year_id = int(selected_year_id) if selected_year_id is not None else None
        except (TypeError, ValueError):
            selected_year_id = None
        if previous_year_id is None and selected_year_id is not None:
            previous_year_id = engine._previous_year_id(con, selected_year_id)
        previous_year = _school_year(con, previous_year_id)

        blockers: list[str] = []
        warnings: list[str] = []
        level_codes = [str(x or "").upper().strip() for x in (plan.get("level_codes") or []) if str(x or "").strip()]
        expected_level_code = level_codes[0] if len(level_codes) == 1 else ""
        if len(level_codes) != 1:
            blockers.append(
                "Phương án liên cấp/không xác định duy nhất cấp học; V4.3 chỉ mở khi có thể khóa đúng nguồn đối chiếu theo từng cấp."
            )
        if str(plan.get("action_type") or "").upper() != "MAPPED":
            blockers.append("V4.3 chỉ mở thực hiện cho phương án MAPPED có nguồn → đích rõ ràng.")
        if str(plan.get("match_status") or "") != "MATCHED":
            blockers.append("Phương án chưa khớp đầy đủ trường trong database.")
        if previous_year is None:
            blockers.append("Không xác định được năm dữ liệu nguồn liền trước năm hiệu lực.")

        involved: list[tuple[str, dict[str, Any]]] = []
        target = dict(plan.get("target_school") or {})
        if target:
            involved.append(("TARGET", target))
        for source in plan.get("source_schools") or []:
            involved.append(("SOURCE", dict(source)))
        if not involved:
            blockers.append("Không xác định được trường nguồn/đích để kiểm tra dữ liệu nguồn.")

        dbctx = _dbctx or _load_db_context(con, previous_year_id)
        checks = [
            _audit_school(
                school=school,
                role=role,
                previous_year=previous_year,
                expected_level_code=expected_level_code,
                registry=registry,
                dbctx=dbctx,
            )
            for role, school in involved
        ]

        for check in checks:
            if check.get("status") != "PASS":
                blockers.append(
                    f"{check.get('school_name')}: không đạt kiểm tra nguồn V4.3 ({len(check.get('issues') or [])} lỗi)."
                )
            warnings.extend(str(x) for x in check.get("warnings") or [])

        result = {
            "plan_id": str(plan.get("id") or plan_id),
            "status": "PASS" if not blockers else "BLOCK",
            "pass": not blockers,
            "message": (
                "KIỂM TRA NGUỒN V4.3 ĐẠT – đủ điều kiện đi tiếp tới mô phỏng/thực hiện."
                if not blockers else
                "KIỂM TRA NGUỒN V4.3 CHƯA ĐẠT – khóa thực hiện sáp nhập."
            ),
            "previous_year": previous_year,
            "expected_level_code": expected_level_code,
            "school_checks": checks,
            "blockers": blockers,
            "warnings": warnings,
            "registry_fingerprint": registry["registry_fingerprint"],
            "registry_summary": source_registry_summary(),
        }
        result["fingerprint"] = _audit_fingerprint(result)
        return result
    finally:
        if own_connection and con is not None:
            con.close()


def audit_official_plans(
    *,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    level_code: str | None = None,
    include_keep: bool = False,
) -> dict[str, Any]:
    plans = list_official_registry_plans(
        school_year_id=school_year_id,
        commune_id=commune_id,
        level_code=level_code,
        display_mode="all",
    )
    if not include_keep:
        plans = [p for p in plans if str(p.get("action_type") or "").upper() != "KEEP"]

    rows: list[dict[str, Any]] = []
    registry = _load_source_registry()
    with engine._connect(read_only=True) as con:
        # Sổ phương án chính thức hiện cùng năm hiệu lực; cache DB context theo năm nguồn
        # để kiểm tra toàn tỉnh không lặp lại việc nạp hàng chục nghìn hồ sơ cho từng nhóm.
        dbctx_by_prev_year: dict[int | None, dict[str, Any]] = {}
        for plan in plans:
            try:
                selected_year_id = plan.get("school_year_id")
                try:
                    selected_year_id = int(selected_year_id) if selected_year_id is not None else None
                except (TypeError, ValueError):
                    selected_year_id = None
                prev_id = engine._previous_year_id(con, selected_year_id) if selected_year_id is not None else None
                if prev_id not in dbctx_by_prev_year:
                    dbctx_by_prev_year[prev_id] = _load_db_context(con, prev_id)
                audit = audit_official_plan_source(
                    str(plan.get("id") or ""), con=con, plan=plan, previous_year_id=prev_id,
                    _registry=registry, _dbctx=dbctx_by_prev_year[prev_id],
                )
            except Exception as exc:
                audit = {
                    "status": "BLOCK",
                    "pass": False,
                    "message": str(exc),
                    "blockers": [str(exc)],
                    "warnings": [],
                    "school_checks": [],
                    "fingerprint": "",
                }
            rows.append({
                "plan": plan,
                "audit": audit,
                "status": audit.get("status"),
                "pass": bool(audit.get("pass")),
            })

    status_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        status_counts[str(row.get("status") or "UNKNOWN")] += 1
    return {
        "rows": rows,
        "total": len(rows),
        "pass_count": int(status_counts.get("PASS", 0)),
        "block_count": int(status_counts.get("BLOCK", 0)),
        "status_counts": dict(status_counts),
        "registry_summary": source_registry_summary(),
    }
