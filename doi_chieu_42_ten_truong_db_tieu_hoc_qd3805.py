from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
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

TARGET_YEAR = "2026-2027"
TARGET_LEVEL = "TH"
OUT_DIR = PROJECT_DIR / "exports" / "Doi_Chieu_42_Ten_Truong_DB_Tieu_Hoc_QD3805"


def norm(value: Any) -> str:
    text = str(value or "").strip().lower().replace("đ", "d")
    text = "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )
    text = text.replace("&", " va ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    # Bỏ các tiền tố hình thức nhưng KHÔNG bỏ tên cấp học.
    text = re.sub(r"\btruong\b", " ", text)
    return " ".join(text.split())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def school_year_id() -> int:
    for y in engine.list_school_years():
        code = str(y.get("code") or y.get("name") or "").replace("–", "-").replace("—", "-")
        if code == TARGET_YEAR:
            return int(y["id"])
    raise RuntimeError(f"Không tìm thấy năm học {TARGET_YEAR}.")


def member_names(plan: dict[str, Any]) -> list[str]:
    out = []
    for x in plan.get("member_schools") or []:
        name = str((x or {}).get("excel_name") or (x or {}).get("name") or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def has_name_problem(plan: dict[str, Any]) -> bool:
    reasons = " | ".join(str(x) for x in (plan.get("batch_blockers") or []))
    return (
        "CHƯA KHỚP TÊN TRƯỜNG DB" in reasons.upper()
        or str(plan.get("match_status") or "").upper() != "MATCHED"
    )


def candidate_list(excel_name: str, commune: str, schools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nn = norm(excel_name)
    nc = norm(commune)
    same_commune = [s for s in schools if norm(s.get("commune_name")) == nc]
    pool = same_commune if same_commune else schools
    scored = []
    for s in pool:
        sn = norm(s.get("name"))
        if not nn or not sn:
            continue
        ratio = SequenceMatcher(None, nn, sn).ratio()
        if nn == sn:
            ratio = 1.0
        elif nn in sn or sn in nn:
            ratio = max(ratio, 0.95)
        if ratio >= 0.60:
            scored.append((ratio, s))
    scored.sort(key=lambda z: (z[0], bool(z[1].get("is_active")), str(z[1].get("name") or "")), reverse=True)
    out = []
    for score, s in scored[:5]:
        out.append({
            "school_id": int(s.get("id")),
            "code": str(s.get("code") or ""),
            "name": str(s.get("name") or ""),
            "commune": str(s.get("commune_name") or ""),
            "is_active": bool(s.get("is_active")),
            "score": round(float(score), 4),
            "normalized_equal": norm(s.get("name")) == nn,
        })
    return out


def classify(cands: list[dict[str, Any]], commune: str) -> str:
    if not cands:
        return "KHONG_CO_UNG_VIEN"
    top = cands[0]
    second = cands[1] if len(cands) > 1 else None
    same_commune = norm(top.get("commune")) == norm(commune)
    margin = float(top["score"]) - (float(second["score"]) if second else 0.0)

    if top.get("normalized_equal") and same_commune:
        return "AN_TOAN_KHOP_CHINH_XAC"
    if float(top["score"]) >= 0.96 and same_commune and margin >= 0.08:
        return "UNG_VIEN_RAT_CAO"
    if float(top["score"]) >= 0.90 and same_commune and margin >= 0.05:
        return "CAN_XEM_LAI_NHE"
    return "CAN_DOI_CHIEU_THU_CONG"


def main() -> None:
    print("=" * 112)
    print("ĐỐI CHIẾU 42 PHƯƠNG ÁN CHƯA KHỚP TÊN TRƯỜNG DB - TIỂU HỌC - QĐ3805")
    print(f"Dự án: {PROJECT_DIR}")
    print(f"Database: {DATABASE_PATH}")
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA MÃ NGUỒN - KHÔNG GHI DATABASE - KHÔNG THỰC HIỆN SÁP NHẬP")
    print("=" * 112)

    yid = school_year_id()
    preview = batch.build_level_batch_preview(school_year_id=yid, level_code=TARGET_LEVEL)
    schools = engine.list_schools(
        year_id=yid,
        commune_id=None,
        level_code=TARGET_LEVEL,
        include_inactive=True,
    )

    rows = []
    seen_ops = set()
    for p in preview.get("rows") or []:
        if str(p.get("batch_state") or "").upper() != "BLOCK":
            continue
        if not has_name_problem(p):
            continue
        op_id = str(p.get("qd3805_operation_id") or "")
        if op_id and op_id in seen_ops:
            continue
        if op_id:
            seen_ops.add(op_id)

        commune = str(p.get("commune_excel") or "")
        members = []
        classes = []
        for name in member_names(p):
            cands = candidate_list(name, commune, schools)
            cls = classify(cands, commune)
            classes.append(cls)
            members.append({
                "excel_name": name,
                "classification": cls,
                "candidates": cands,
            })

        if members and all(x["classification"] == "AN_TOAN_KHOP_CHINH_XAC" for x in members):
            operation_class = "AN_TOAN_KHOP_CHINH_XAC"
        elif members and all(x["classification"] in {"AN_TOAN_KHOP_CHINH_XAC", "UNG_VIEN_RAT_CAO"} for x in members):
            operation_class = "UNG_VIEN_RAT_CAO"
        elif any(x["classification"] == "KHONG_CO_UNG_VIEN" for x in members):
            operation_class = "KHONG_CO_UNG_VIEN"
        else:
            operation_class = "CAN_DOI_CHIEU"

        rows.append({
            "qd3805_operation_id": op_id,
            "plan_id": str(p.get("id") or ""),
            "commune": commune,
            "plan_text": str(p.get("plan_text") or ""),
            "match_status": str(p.get("match_status") or ""),
            "match_label": str(p.get("match_label") or ""),
            "operation_classification": operation_class,
            "members": members,
            "blockers": [str(x) for x in (p.get("batch_blockers") or [])],
        })

    counter = Counter(x["operation_classification"] for x in rows)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_dir": str(PROJECT_DIR),
        "database_path": str(DATABASE_PATH),
        "database_sha256": sha256_file(Path(DATABASE_PATH)) if Path(DATABASE_PATH).exists() else None,
        "school_year": TARGET_YEAR,
        "level_code": TARGET_LEVEL,
        "summary": {
            "name_problem_operations": len(rows),
            "classification_counts": dict(sorted(counter.items())),
            "qd3805_expected_actions": int(preview.get("registry_action_expected_count") or 0),
            "qd3805_mapped_actions": int(preview.get("registry_action_mapped_count") or 0),
            "effective_block_count": int(preview.get("effective_block_count") or 0),
        },
        "rows": rows,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUT_DIR / f"doi_chieu_42_ten_truong_db_TH_QD3805_{stamp}.json"
    txt_path = OUT_DIR / f"tom_tat_42_ten_truong_db_TH_QD3805_{stamp}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = []
    lines.append("ĐỐI CHIẾU 42 PHƯƠNG ÁN CHƯA KHỚP TÊN TRƯỜNG DB - TIỂU HỌC - QĐ3805")
    lines.append("=" * 96)
    lines.append(f"Tổng operation có vấn đề tên DB: {len(rows)}")
    for k, v in sorted(counter.items(), key=lambda z: (-z[1], z[0])):
        lines.append(f"{k}: {v}")
    lines.append("")
    lines.append("CHI TIẾT:")
    for row in rows:
        lines.append("-" * 96)
        lines.append(f"{row['qd3805_operation_id']} | {row['commune']} | {row['plan_text']}")
        lines.append(f"Phân loại operation: {row['operation_classification']}")
        for m in row["members"]:
            lines.append(f"  Excel: {m['excel_name']} | {m['classification']}")
            for c in m["candidates"][:3]:
                lines.append(
                    f"    -> DB: {c['name']} | mã={c['code']} | school_id={c['school_id']} | "
                    f"xã={c['commune']} | active={c['is_active']} | score={c['score']}"
                )
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Tổng operation có vấn đề tên DB: {len(rows)}")
    for k, v in sorted(counter.items(), key=lambda z: (-z[1], z[0])):
        print(f"{k}: {v}")
    print("-" * 112)
    print("Database: KHÔNG THAY ĐỔI")
    print("Báo cáo JSON:", json_path)
    print("Tóm tắt TXT:", txt_path)
    print("=" * 112)


if __name__ == "__main__":
    main()
