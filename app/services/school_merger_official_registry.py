from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from app.database import DATABASE_PATH


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
REGISTRY_FILE = PROJECT_DIR / "data" / "school_merger_official_registry.json"
LEVEL_LOCK_FILE = PROJECT_DIR / "data" / "school_merger_registry" / "qd3805_level_lock.json"

OFFICIAL_DOCUMENT_CODE = "PA SẮP XẾP 2026"
OFFICIAL_DOCUMENT_TITLE = (
    "Phụ lục 1 - Phương án sắp xếp tổng thể cơ sở giáo dục mầm non, "
    "tiểu học, THCS công lập trên địa bàn tỉnh"
)


class SchoolMergerRegistryError(RuntimeError):
    pass


def _connect() -> sqlite3.Connection:
    uri = DATABASE_PATH.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _normalize(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _bare_commune(value: Any) -> str:
    text = _normalize(value)
    return re.sub(r"^(xa|phuong|thi tran|thi xa|thanh pho)\s+", "", text)


def _school_key(value: Any) -> str:
    text = _normalize(value)
    text = re.sub(r"^truong\s+", "", text)
    text = re.sub(r"\bth\b", "tieu hoc", text)
    text = re.sub(r"\bttr\b", "thi tran", text)
    text = re.sub(r"\btt\b", "thi tran", text)
    return " ".join(text.split())


def _load_registry() -> dict[str, Any]:
    if not REGISTRY_FILE.exists():
        raise SchoolMergerRegistryError(f"Không tìm thấy sổ phương án: {REGISTRY_FILE}")
    try:
        payload = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SchoolMergerRegistryError(f"Không đọc được sổ phương án: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("plans"), list):
        raise SchoolMergerRegistryError("Sổ phương án không đúng cấu trúc JSON.")
    return payload


def _load_level_lock_index() -> dict[int, list[str]]:
    """Excel row -> mã trường QĐ3805. Không ghi DB, không suy đoán bằng tên."""
    if not LEVEL_LOCK_FILE.exists():
        return {}
    try:
        payload = json.loads(LEVEL_LOCK_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[int, list[str]] = {}
    for op in payload.get("operations") or []:
        if not isinstance(op, dict):
            continue
        for school in op.get("source_schools") or []:
            if not isinstance(school, dict):
                continue
            try:
                excel_row = int(school.get("excel_row"))
            except (TypeError, ValueError):
                continue
            codes = []
            for value in school.get("codes") or []:
                code = str(value or "").strip()
                if code and code not in codes:
                    codes.append(code)
            if codes:
                out[excel_row] = codes
    return out



def _load_mn_action_lock_operations() -> list[dict[str, Any]]:
    """QĐ3805: Mầm non là batch thuần MN, không có liên cấp."""
    if not LEVEL_LOCK_FILE.exists():
        return []
    try:
        payload = json.loads(LEVEL_LOCK_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for raw in payload.get("operations") or []:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("batch") or "").strip().upper() != "MN":
            continue
        levels = {
            str(x or "").strip().upper()
            for x in (raw.get("source_levels") or [])
            if str(x or "").strip()
        }
        target_levels = {
            str(x or "").strip().upper()
            for x in (raw.get("target_levels") or [])
            if str(x or "").strip()
        }
        if levels and levels != {"MN"}:
            continue
        if target_levels and target_levels != {"MN"}:
            continue
        out.append(dict(raw))
    return out


def _excel_row_value(item: dict[str, Any]) -> int | None:
    try:
        return int(item.get("excel_row"))
    except (TypeError, ValueError):
        return None


def _match_mn_lock_operation(
    raw: dict[str, Any],
    raw_members: list[dict[str, Any]],
    mn_ops: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Khóa plan MN bằng chính các dòng Excel thuộc operation QĐ3805."""
    member_rows = {
        x for x in (_excel_row_value(m) for m in raw_members)
        if x is not None
    }
    if not member_rows:
        return None

    scored = []
    raw_commune = _bare_commune(raw.get("commune_excel"))
    for op in mn_ops:
        op_rows = {
            x for x in (
                _excel_row_value(dict(s))
                for s in (op.get("source_schools") or [])
                if isinstance(s, dict)
            )
            if x is not None
        }
        overlap = member_rows & op_rows
        if not overlap:
            continue
        score = len(overlap) * 100
        if op_rows and op_rows.issubset(member_rows):
            score += 1000
        if raw_commune and raw_commune == _bare_commune(op.get("commune")):
            score += 50
        scored.append((score, str(op.get("operation_id") or ""), op))

    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top = scored[0][0]
    best = [x[2] for x in scored if x[0] == top]
    return best[0] if len(best) == 1 else None


def _filter_raw_members_by_mn_lock(
    raw_members: list[dict[str, Any]],
    op: dict[str, Any],
) -> list[dict[str, Any]]:
    allowed_rows = {
        x for x in (
            _excel_row_value(dict(s))
            for s in (op.get("source_schools") or [])
            if isinstance(s, dict)
        )
        if x is not None
    }
    if not allowed_rows:
        return raw_members
    return [
        m for m in raw_members
        if _excel_row_value(m) in allowed_rows
    ]


def _resolve_mn_target_index(
    members: list[dict[str, Any]],
    op: dict[str, Any],
) -> int | None:
    """Ưu tiên mã đích QĐ3805, sau đó mới dùng tên đích đã khóa."""
    target_codes = {
        str(x or "").strip()
        for x in (op.get("target_codes") or [])
        if str(x or "").strip()
    }
    if target_codes:
        hits = []
        for idx, member in enumerate(members):
            member_codes = {
                str(x or "").strip()
                for x in (member.get("official_codes") or [])
                if str(x or "").strip()
            }
            db_code = str(member.get("code") or "").strip()
            if db_code:
                member_codes.add(db_code)
            if member_codes & target_codes:
                hits.append(idx)
        if len(hits) == 1:
            return hits[0]

    target_text = _school_key(op.get("target_text") or op.get("official_plan") or "")
    if target_text:
        hits = [
            idx for idx, member in enumerate(members)
            if _school_key(
                member.get("excel_name")
                or member.get("name")
                or ""
            ) == target_text
        ]
        if len(hits) == 1:
            return hits[0]
    return None


def _school_year_id(con: sqlite3.Connection, code: str) -> int | None:
    row = con.execute(
        "SELECT id FROM school_years WHERE REPLACE(REPLACE(code,'–','-'),'—','-')=? LIMIT 1",
        (str(code or "").replace("–", "-").replace("—", "-"),),
    ).fetchone()
    return int(row[0]) if row else None


def _match_commune(con: sqlite3.Connection, excel_name: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    rows = [dict(r) for r in con.execute(
        "SELECT id,code,name,is_active FROM communes ORDER BY name COLLATE NOCASE"
    ).fetchall()]
    wanted = _bare_commune(excel_name)
    matches = [r for r in rows if _bare_commune(r.get("name")) == wanted]
    return (matches[0] if len(matches) == 1 else None), matches


def _all_schools_in_commune(con: sqlite3.Connection, commune_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in con.execute(
        "SELECT id,code,name,commune_id,is_active FROM schools WHERE commune_id=? ORDER BY name COLLATE NOCASE",
        (int(commune_id),),
    ).fetchall()]


def _schools_for_codes(con: sqlite3.Connection, codes: list[str]) -> list[dict[str, Any]]:
    cleaned = [str(x or "").strip() for x in codes if str(x or "").strip()]
    if not cleaned:
        return []
    placeholders = ",".join("?" for _ in cleaned)
    rows = con.execute(
        "SELECT s.id,s.code,s.name,s.commune_id,s.is_active,c.name AS commune_name "
        "FROM schools s LEFT JOIN communes c ON c.id=s.commune_id "
        f"WHERE s.code IN ({placeholders}) ORDER BY s.id",
        tuple(cleaned),
    ).fetchall()
    return [dict(r) for r in rows]


def _choose_by_official_code(
    con: sqlite3.Connection,
    *,
    codes: list[str],
    excel_name: str,
    commune_excel: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    rows = _schools_for_codes(con, codes)
    if len(rows) == 1:
        return rows[0], rows
    if not rows:
        return None, []

    wanted_commune = _bare_commune(commune_excel)
    same_commune = [r for r in rows if _bare_commune(r.get("commune_name")) == wanted_commune]
    if len(same_commune) == 1:
        return same_commune[0], rows

    wanted_key = _school_key(excel_name)
    same_name = [r for r in rows if _school_key(r.get("name")) == wanted_key]
    if len(same_name) == 1:
        return same_name[0], rows
    return None, rows


def _match_school(candidates: list[dict[str, Any]], excel_name: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    wanted_norm = _normalize(excel_name)
    exact = [r for r in candidates if _normalize(r.get("name")) == wanted_norm]
    if len(exact) == 1:
        return exact[0], exact

    wanted_key = _school_key(excel_name)
    keyed = [r for r in candidates if _school_key(r.get("name")) == wanted_key]
    if len(keyed) == 1:
        return keyed[0], keyed

    return None, keyed or exact


def _fallback_school(member: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": None,
        "code": "",
        "name": str(member.get("school_name") or ""),
        "commune_id": None,
        "is_active": True,
        "db_matched": False,
        "excel_name": str(member.get("school_name") or ""),
        "class_count": member.get("class_count"),
        "excel_row": member.get("excel_row"),
        "stt": member.get("stt"),
        "note": str(member.get("note") or ""),
        "match_candidates": [],
        "match_method": "UNMATCHED",
        "official_codes": [],
    }


def _member_with_db(
    member: dict[str, Any],
    *,
    con: sqlite3.Connection,
    candidates: list[dict[str, Any]],
    commune_excel: str,
    level_lock_index: dict[int, list[str]],
) -> dict[str, Any]:
    try:
        excel_row = int(member.get("excel_row"))
    except (TypeError, ValueError):
        excel_row = -1
    official_codes = list(level_lock_index.get(excel_row) or [])

    if official_codes:
        matched, possible = _choose_by_official_code(
            con,
            codes=official_codes,
            excel_name=str(member.get("school_name") or ""),
            commune_excel=commune_excel,
        )
        if matched is not None:
            item = dict(matched)
            item.update({
                "db_matched": True,
                "excel_name": str(member.get("school_name") or ""),
                "class_count": member.get("class_count"),
                "excel_row": member.get("excel_row"),
                "stt": member.get("stt"),
                "note": str(member.get("note") or ""),
                "match_candidates": [],
                "match_method": "QD3805_CODE",
                "official_codes": official_codes,
            })
            return item
        # Có mã chính thức nhưng không đủ điều kiện chọn duy nhất -> không hạ xuống đoán tên.
        item = _fallback_school(member)
        item["official_codes"] = official_codes
        item["match_method"] = "QD3805_CODE_AMBIGUOUS"
        item["match_candidates"] = [
            {"id": x.get("id"), "code": x.get("code"), "name": x.get("name")}
            for x in possible[:5]
        ]
        return item

    # Fallback tương thích cho MN/THCS hoặc dữ liệu chưa được bổ sung mã.
    matched, possible = _match_school(candidates, str(member.get("school_name") or ""))
    if matched is None:
        item = _fallback_school(member)
        item["match_candidates"] = [
            {"id": x.get("id"), "code": x.get("code"), "name": x.get("name")}
            for x in possible[:5]
        ]
        item["match_method"] = "NAME_FALLBACK_UNMATCHED"
        return item

    item = dict(matched)
    item.update({
        "db_matched": True,
        "excel_name": str(member.get("school_name") or ""),
        "class_count": member.get("class_count"),
        "excel_row": member.get("excel_row"),
        "stt": member.get("stt"),
        "note": str(member.get("note") or ""),
        "match_candidates": [],
        "match_method": "NAME_FALLBACK",
        "official_codes": [],
    })
    return item


def _display_mode_match(action_type: str, display_mode: str) -> bool:
    mode = str(display_mode or "all").strip().lower()
    action = str(action_type or "").strip().upper()
    if mode == "all":
        return True
    if mode == "keep":
        return action == "KEEP"
    if mode == "mapped":
        return action == "MAPPED"
    if mode == "special":
        return action == "SPECIAL"
    return True


def list_official_registry_plans(
    *,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    level_code: str | None = None,
    display_mode: str = "all",
) -> list[dict[str, Any]]:
    payload = _load_registry()
    level_lock_index = _load_level_lock_index()
    mn_lock_operations = _load_mn_action_lock_operations()
    wanted_level = str(level_code or "").strip().upper()
    result: list[dict[str, Any]] = []

    with _connect() as con:
        for raw in payload.get("plans") or []:
            if not isinstance(raw, dict):
                continue
            if not _display_mode_match(str(raw.get("action_type") or ""), display_mode):
                continue

            levels = [str(x or "").strip().upper() for x in (raw.get("level_codes") or [])]
            if wanted_level and wanted_level not in levels:
                continue

            year_code = str(raw.get("school_year_code") or payload.get("school_year_code") or "")
            year_id = _school_year_id(con, year_code)
            if school_year_id is not None and year_id != int(school_year_id):
                continue

            commune_excel = str(raw.get("commune_excel") or "")
            commune, commune_candidates = _match_commune(con, commune_excel)
            actual_commune_id = int(commune["id"]) if commune else None
            if commune_id is not None and actual_commune_id != int(commune_id):
                continue

            school_candidates = _all_schools_in_commune(con, actual_commune_id) if actual_commune_id else []

            raw_members = [
                dict(m)
                for m in (raw.get("members") or [])
                if isinstance(m, dict)
            ]

            # Mầm non không có liên cấp. Với mọi operation thuần MN, bảng khóa QĐ3805
            # là nguồn thẩm quyền xác định CHÍNH XÁC các dòng trường thuộc operation.
            # Điều này loại an toàn các dòng cấp khác nằm sát vùng Excel nhưng bị registry
            # cũ gom nhầm vào cùng plan (ví dụ Tiểu học Đồng Thành sau OP-0680).
            mn_lock_op = _match_mn_lock_operation(raw, raw_members, mn_lock_operations)
            if mn_lock_op is not None:
                raw_members = _filter_raw_members_by_mn_lock(raw_members, mn_lock_op)

            members = [
                _member_with_db(
                    dict(m),
                    con=con,
                    candidates=school_candidates,
                    commune_excel=commune_excel,
                    level_lock_index=level_lock_index,
                )
                for m in raw_members
            ]

            if mn_lock_op is not None:
                target_index = _resolve_mn_target_index(members, mn_lock_op)
            else:
                target_index = raw.get("target_member_index")
                try:
                    target_index = int(target_index) if target_index is not None else None
                except (TypeError, ValueError):
                    target_index = None
            target_school = (
                members[target_index]
                if target_index is not None and 0 <= target_index < len(members)
                else None
            )
            source_schools = [
                m for idx, m in enumerate(members)
                if target_index is not None and idx != target_index
            ]

            matched_count = sum(1 for m in members if m.get("db_matched"))
            code_matched_count = sum(1 for m in members if m.get("match_method") == "QD3805_CODE")
            if commune is None:
                match_label = "CHƯA KHỚP ĐỊA BÀN DB"
                match_status = "UNMATCHED_COMMUNE"
            elif matched_count == len(members) and members:
                if code_matched_count:
                    match_label = "KHỚP ĐỦ TRƯỜNG TRONG DB THEO MÃ QĐ3805"
                else:
                    match_label = "KHỚP ĐỦ TRƯỜNG TRONG DB"
                match_status = "MATCHED"
            elif matched_count:
                match_label = f"KHỚP {matched_count}/{len(members)} TRƯỜNG"
                match_status = "PARTIAL"
            else:
                match_label = "CHƯA KHỚP TRƯỜNG DB"
                match_status = "UNMATCHED_SCHOOL"

            item = dict(raw)
            if mn_lock_op is not None:
                # Khóa lại metadata cấp học theo operation QĐ3805 thuần MN.
                item["level_codes"] = ["MN"]
                item["qd3805_mn_lock_operation_id"] = str(
                    mn_lock_op.get("operation_id") or ""
                )
                item["qd3805_mn_lock_member_rows"] = sorted(
                    x for x in (
                        _excel_row_value(dict(s))
                        for s in (mn_lock_op.get("source_schools") or [])
                        if isinstance(s, dict)
                    )
                    if x is not None
                )
            item.update({
                "school_year_id": year_id,
                "document_code": OFFICIAL_DOCUMENT_CODE,
                "document_title": OFFICIAL_DOCUMENT_TITLE,
                "commune_id": actual_commune_id,
                "commune_name": str(commune.get("name") or "") if commune else commune_excel,
                "commune_db": commune,
                "commune_match_candidates": commune_candidates,
                "member_schools": members,
                "target_school": target_school,
                "source_schools": source_schools,
                "match_status": match_status,
                "match_label": match_label,
                "matched_school_count": matched_count,
                "code_matched_school_count": code_matched_count,
                "total_school_count": len(members),
                "execution_locked": True,
                "effective_status": "OFFICIAL_V2_REVIEW",
                "status_label": "PHƯƠNG ÁN CHÍNH THỨC – ĐỐI CHIẾU",
            })
            result.append(item)

    result.sort(key=lambda x: (
        int(x.get("commune_id") or 10**9),
        int(x.get("first_sttt") or x.get("first_stt") or 0),
        str(x.get("id") or ""),
    ))
    return result


def official_registry_summary() -> dict[str, Any]:
    payload = _load_registry()
    plans = [x for x in payload.get("plans") or [] if isinstance(x, dict)]
    return {
        "source_file": payload.get("source_file"),
        "source_sheet": payload.get("source_sheet"),
        "school_year_code": payload.get("school_year_code"),
        "group_count": len(plans),
        "execution_enabled": False,
    }
