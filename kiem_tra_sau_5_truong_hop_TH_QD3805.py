# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
if not (PROJECT_DIR / "app").exists():
    PROJECT_DIR = Path.cwd()
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.database import DATABASE_PATH  # noqa: E402
from app.services import school_merger_service as engine  # noqa: E402
from app.services import school_merger_level_batch_service as batch  # noqa: E402
from app.services.school_merger_source_audit_service import audit_official_plans  # noqa: E402

TARGET_YEAR = "2026-2027"
PREV_YEAR = "2025-2026"
TARGET_LEVEL = "TH"

TARGET_OPS = {
    "QD3805-OP-0415": "TRI_LE_RENAME_OR_SPECIAL",
    "QD3805-OP-0587": "THANH_LINH_DUPLICATE_STAFF_CODE",
    "QD3805-OP-0032": "NGHI_LIEN_DUPLICATE_STAFF_CODE",
    "QD3805-OP-0339": "NGHI_VAN_INACTIVE_SOURCE",
    "QD3805-OP-0340": "NGHI_HOA_INACTIVE_SOURCE",
}

PEOPLE = [
    "Lê Văn Hạnh",
    "Võ Xuân Nguyên",
    "Lê Sĩ Bản",
    "Tô Thị Thuỷ",
]
STAFF_CODES = ["4000679209", "4002555491"]

OUT_DIR = PROJECT_DIR / "exports" / "Kiem_Tra_Sau_5_Truong_Hop_TH_QD3805"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ro_connect() -> sqlite3.Connection:
    p = Path(DATABASE_PATH).resolve()
    con = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def safe(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [safe(x) for x in v]
    if hasattr(v, "keys"):
        try:
            return {str(k): safe(v[k]) for k in v.keys()}
        except Exception:
            pass
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def year_ids(con: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for r in con.execute("SELECT id,code FROM school_years").fetchall():
        code = str(r["code"] or "").replace("–", "-").replace("—", "-")
        out[code] = int(r["id"])
    return out


def school_year_id() -> int:
    for y in engine.list_school_years():
        code = str(y.get("code") or y.get("name") or "").replace("–", "-").replace("—", "-")
        if code == TARGET_YEAR:
            return int(y["id"])
    raise RuntimeError(f"Không tìm thấy năm học {TARGET_YEAR}.")


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone() is not None


def table_cols(con: sqlite3.Connection, table: str) -> list[str]:
    return [str(r["name"]) for r in con.execute(f"PRAGMA table_info({table})").fetchall()]


def search_person_and_codes(con: sqlite3.Connection) -> list[dict[str, Any]]:
    """Quét các bảng có cột text để tìm đúng 4 tên và 2 mã; chỉ đọc."""
    tables = [str(r["name"]) for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]
    hits = []

    wanted_names = {x.lower(): x for x in PEOPLE}
    wanted_codes = set(STAFF_CODES)

    for table in tables:
        cols = table_cols(con, table)
        if not cols:
            continue
        # Ưu tiên các bảng có dấu hiệu nhân sự.
        score = sum(
            1 for c in cols
            if c.lower() in {
                "staff_code", "full_name", "name", "school_id", "school_year_id",
                "birth_date", "date_of_birth", "employee_code", "person_code"
            }
        )
        if score == 0 and "staff" not in table.lower() and "teacher" not in table.lower():
            continue

        text_cols = []
        for c in cols:
            lc = c.lower()
            if any(k in lc for k in ("name", "code", "staff", "person", "employee")):
                text_cols.append(c)
        if not text_cols:
            continue

        where_parts = []
        params = []
        for c in text_cols:
            for name in PEOPLE:
                where_parts.append(f"lower(CAST({c} AS TEXT))=lower(?)")
                params.append(name)
            for code in STAFF_CODES:
                where_parts.append(f"CAST({c} AS TEXT)=?")
                params.append(code)
        sql = f"SELECT * FROM {table} WHERE " + " OR ".join(where_parts)
        try:
            rows = con.execute(sql, tuple(params)).fetchall()
        except Exception:
            continue

        for row in rows:
            d = dict(row)
            # Xác nhận row thật sự có một trong 4 tên hoặc 2 mã.
            blob_values = [str(v or "") for v in d.values()]
            if not (
                any(v.lower() in wanted_names for v in blob_values)
                or any(v in wanted_codes for v in blob_values)
            ):
                continue
            hits.append({
                "table": table,
                "row": safe(d),
            })
    return hits


def school_table_counts(
    con: sqlite3.Connection,
    school_ids: list[int],
    yids: dict[str, int],
) -> list[dict[str, Any]]:
    """Đếm dấu vết dữ liệu của nguồn/đích trên mọi bảng có school_id."""
    wanted = [int(x) for x in school_ids if x is not None]
    if not wanted:
        return []

    tables = [str(r["name"]) for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]
    out = []
    placeholders = ",".join("?" for _ in wanted)

    for table in tables:
        cols = table_cols(con, table)
        if "school_id" not in cols:
            continue
        try:
            total_rows = con.execute(
                f"SELECT school_id,COUNT(*) AS n FROM {table} "
                f"WHERE school_id IN ({placeholders}) GROUP BY school_id",
                tuple(wanted),
            ).fetchall()
        except Exception:
            continue

        total_map = {int(r["school_id"]): int(r["n"]) for r in total_rows}
        if not total_map:
            continue

        item = {
            "table": table,
            "totals": total_map,
        }

        year_col = None
        for c in ("school_year_id", "year_id"):
            if c in cols:
                year_col = c
                break
        if year_col:
            by_year = {}
            for code in (PREV_YEAR, TARGET_YEAR):
                yid = yids.get(code)
                if yid is None:
                    continue
                try:
                    rows = con.execute(
                        f"SELECT school_id,COUNT(*) AS n FROM {table} "
                        f"WHERE school_id IN ({placeholders}) AND {year_col}=? "
                        f"GROUP BY school_id",
                        tuple(wanted) + (int(yid),),
                    ).fetchall()
                    by_year[code] = {
                        int(r["school_id"]): int(r["n"])
                        for r in rows
                    }
                except Exception:
                    pass
            item["by_year"] = by_year

        out.append(item)
    return out


def schools_like(con: sqlite3.Connection, pattern: str) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT s.id,s.code,s.name,s.is_active,s.commune_id,c.name AS commune_name "
        "FROM schools s LEFT JOIN communes c ON c.id=s.commune_id "
        "WHERE lower(s.name) LIKE lower(?) ORDER BY s.name,s.id",
        (f"%{pattern}%",),
    ).fetchall()
    return [dict(r) for r in rows]


def main() -> None:
    print("=" * 118)
    print("KIỂM TRA SÂU 5 TRƯỜNG HỢP CÒN LẠI - TIỂU HỌC - QĐ3805")
    print("Database:", DATABASE_PATH)
    print("Chế độ: CHỈ ĐỌC / KHÔNG SỬA SOURCE / KHÔNG GHI DATABASE / KHÔNG SÁP NHẬP")
    print("=" * 118)

    dbp = Path(DATABASE_PATH)
    before = sha256_file(dbp)
    yid = school_year_id()

    preview = batch.build_level_batch_preview(
        school_year_id=yid,
        level_code=TARGET_LEVEL,
    )
    preview_rows = {
        str(x.get("qd3805_operation_id") or ""): dict(x)
        for x in (preview.get("rows") or [])
        if str(x.get("qd3805_operation_id") or "") in TARGET_OPS
    }

    audit = audit_official_plans(
        school_year_id=yid,
        commune_id=None,
        level_code=TARGET_LEVEL,
    )
    audit_map = {
        str((x.get("plan") or {}).get("id") or ""): safe(x.get("audit") or {})
        for x in (audit.get("rows") or [])
    }

    with ro_connect() as con:
        yids = year_ids(con)
        people_hits = search_person_and_codes(con)

        op_details = []
        for op_id, purpose in TARGET_OPS.items():
            p = preview_rows.get(op_id) or {}
            source_ids = []
            for s in p.get("source_schools") or []:
                try:
                    source_ids.append(int((s or {}).get("id")))
                except Exception:
                    pass
            try:
                target_id = int((p.get("target_school") or {}).get("id"))
            except Exception:
                target_id = None

            ids = list(dict.fromkeys(source_ids + ([target_id] if target_id is not None else [])))
            pid = str(p.get("id") or "")

            op_details.append({
                "operation_id": op_id,
                "purpose": purpose,
                "plan_id": pid,
                "commune": str(p.get("commune_excel") or p.get("commune_name") or ""),
                "plan_text": str(p.get("plan_text") or ""),
                "batch_state": str(p.get("batch_state") or ""),
                "batch_blockers": safe(p.get("batch_blockers") or []),
                "source_schools": safe(p.get("source_schools") or []),
                "target_school": safe(p.get("target_school") or {}),
                "source_audit_full": audit_map.get(pid) or {},
                "school_table_counts": school_table_counts(con, ids, yids),
            })

        tri_le_schools = schools_like(con, "Tri Lễ")
        nghi_van_schools = schools_like(con, "Nghi Vạn")
        nghi_hoa_schools = schools_like(con, "Nghi Hoa")
        nghi_trung_schools = schools_like(con, "Nghi Trung")
        nghi_dien_schools = schools_like(con, "Nghi Diên")

    after = sha256_file(dbp)
    unchanged = before == after

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database_unchanged": unchanged,
        "people_and_code_hits": people_hits,
        "operations": op_details,
        "school_lookup": {
            "Tri Lễ": safe(tri_le_schools),
            "Nghi Vạn": safe(nghi_van_schools),
            "Nghi Hoa": safe(nghi_hoa_schools),
            "Nghi Trung": safe(nghi_trung_schools),
            "Nghi Diên": safe(nghi_dien_schools),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jp = OUT_DIR / f"bao_cao_sau_5_truong_hop_TH_QD3805_{stamp}.json"
    tp = OUT_DIR / f"tom_tat_sau_5_truong_hop_TH_QD3805_{stamp}.txt"
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        "KIỂM TRA SÂU 5 TRƯỜNG HỢP CÒN LẠI - TIỂU HỌC - QĐ3805",
        "=" * 112,
        "",
        "A. 4 NHÂN SỰ / 2 MÃ GÂY XUNG ĐỘT - DỮ LIỆU DB:",
    ]
    if people_hits:
        for hit in people_hits:
            lines.append("-" * 112)
            lines.append("Bảng: " + hit["table"])
            lines.append(json.dumps(hit["row"], ensure_ascii=False, default=str))
    else:
        lines.append("Không tìm thấy bản ghi phù hợp trong các bảng nhân sự có thể nhận diện.")

    lines.append("")
    lines.append("B. 5 OPERATION CÒN LẠI:")
    for d in op_details:
        lines.append("-" * 112)
        lines.append(
            f"{d['operation_id']} | {d['purpose']} | {d['commune']} | "
            f"{d['plan_text']} | state={d['batch_state']} | plan_id={d['plan_id']}"
        )
        lines.append("Nguồn:")
        for s in d["source_schools"] or []:
            lines.append(
                f"  - school_id={s.get('id')} | mã={s.get('code')} | "
                f"{s.get('name')} | active={s.get('is_active')}"
            )
        t = d["target_school"] or {}
        if t:
            lines.append(
                f"Đích: school_id={t.get('id')} | mã={t.get('code')} | "
                f"{t.get('name')} | active={t.get('is_active')}"
            )
        else:
            lines.append("Đích: CHƯA XÁC ĐỊNH")

        audit_full = d.get("source_audit_full") or {}
        if audit_full:
            lines.append("SOURCE AUDIT FULL:")
            lines.append(json.dumps(audit_full, ensure_ascii=False, default=str))

        if d["school_table_counts"]:
            lines.append("DẤU VẾT DỮ LIỆU THEO school_id:")
            for c in d["school_table_counts"]:
                lines.append(
                    f"  - {c['table']} | totals={json.dumps(c.get('totals'), ensure_ascii=False)} "
                    f"| by_year={json.dumps(c.get('by_year') or {}, ensure_ascii=False)}"
                )
        else:
            lines.append("DẤU VẾT DỮ LIỆU THEO school_id: không có bảng nào có bản ghi.")

    lines.append("")
    lines.append("C. TRA CỨU TRƯỜNG LIÊN QUAN:")
    for key, arr in report["school_lookup"].items():
        lines.append("-" * 112)
        lines.append(key + ":")
        for s in arr:
            lines.append(
                f"  - school_id={s.get('id')} | mã={s.get('code')} | "
                f"{s.get('name')} | active={s.get('is_active')} | {s.get('commune_name')}"
            )

    lines.append("")
    lines.append("-" * 112)
    lines.append("Database: " + ("KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH THAY ĐỔI"))
    lines.append("JSON: " + str(jp))
    lines.append("TXT: " + str(tp))
    tp.write_text("\n".join(lines), encoding="utf-8")

    print("Đã kiểm tra 5 operation.")
    print("Số bản ghi DB khớp 4 tên/2 mã nhân sự:", len(people_hits))
    print("Database:", "KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH THAY ĐỔI")
    print("TXT:", tp)
    print("=" * 118)

    if not unchanged:
        raise SystemExit("DỪNG: hash database thay đổi ngoài dự kiến.")


if __name__ == "__main__":
    main()
