# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
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

TARGET_YEAR = "2026-2027"
TARGET_LEVEL = "TH"

LEVEL_LOCK = (
    PROJECT_DIR
    / "data"
    / "school_merger_registry"
    / "qd3805_level_lock.json"
)

OUT_DIR = (
    PROJECT_DIR
    / "exports"
    / "Doi_Chieu_42_Bang_Ma_Truong_QD3805"
)


def norm(v: Any) -> str:
    s = str(v or "").strip().lower().replace("đ", "d")
    s = "".join(
        ch
        for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn"
    )
    s = s.replace("&", " va ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\btruong\b", " ", s)
    return " ".join(s.split())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def school_year_id() -> int:
    for y in engine.list_school_years():
        code = str(y.get("code") or y.get("name") or "")
        code = code.replace("–", "-").replace("—", "-")
        if code == TARGET_YEAR:
            return int(y["id"])
    raise RuntimeError(f"Không tìm thấy năm học {TARGET_YEAR}.")


def load_lock() -> dict[str, Any]:
    if not LEVEL_LOCK.exists():
        raise RuntimeError(
            "Không tìm thấy qd3805_level_lock.json tại: "
            + str(LEVEL_LOCK)
        )
    return json.loads(LEVEL_LOCK.read_text(encoding="utf-8"))


def has_name_problem(plan: dict[str, Any]) -> bool:
    reasons = " | ".join(
        str(x) for x in (plan.get("batch_blockers") or [])
    ).upper()
    return (
        "CHƯA KHỚP TÊN TRƯỜNG DB" in reasons
        or "KHỚP TÊN TRƯỜNG DB" in reasons
        or str(plan.get("match_status") or "").upper() != "MATCHED"
    )


def school_rows_for_level(
    year_id: int,
    level_code: str,
) -> list[dict[str, Any]]:
    rows = engine.list_schools(
        year_id=year_id,
        commune_id=None,
        level_code=level_code,
        include_inactive=True,
    )
    return [dict(x) for x in rows]


def code_values(item: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for x in item.get("codes") or []:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def classify_code_match(
    official_school: dict[str, Any],
    db_matches: list[dict[str, Any]],
    official_commune: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    off_name = str(official_school.get("name") or "").strip()

    if not db_matches:
        return "KHONG_TIM_THAY_MA_TRONG_DB", [
            "Không có trường DB nào mang mã QĐ3805 này."
        ]

    if len(db_matches) > 1:
        return "TRUNG_MA_TRONG_DB", [
            f"Mã QĐ3805 khớp {len(db_matches)} bản ghi DB; không tự chọn."
        ]

    db = db_matches[0]
    db_name = str(db.get("name") or "").strip()
    db_commune = str(db.get("commune_name") or "").strip()

    same_name = norm(off_name) == norm(db_name)
    same_commune = norm(official_commune) == norm(db_commune)
    active = bool(db.get("is_active"))

    if same_name and same_commune:
        if active:
            return "KHOP_MA_TEN_DIA_BAN_DUY_NHAT", []
        return "KHOP_MA_TEN_DIA_BAN_NHUNG_INACTIVE", [
            "Mã, tên và địa bàn đều khớp nhưng trường DB đang inactive/đã sáp nhập."
        ]

    if same_commune and not same_name:
        reasons.append(
            f"Mã khớp duy nhất, cùng địa bàn nhưng tên khác: "
            f"QĐ3805='{off_name}' / DB='{db_name}'."
        )
        return "KHOP_MA_CUNG_DIA_BAN_KHAC_TEN", reasons

    if same_name and not same_commune:
        reasons.append(
            f"Mã và tên khớp nhưng địa bàn khác: "
            f"QĐ3805='{official_commune}' / DB='{db_commune}'."
        )
        return "KHOP_MA_TEN_KHAC_DIA_BAN", reasons

    reasons.append(
        f"Mã khớp duy nhất nhưng tên và/hoặc địa bàn khác: "
        f"QĐ3805='{off_name}' / DB='{db_name}', "
        f"QĐ3805 xã='{official_commune}' / DB xã='{db_commune}'."
    )
    return "KHOP_MA_NHUNG_CAN_DOI_CHIEU", reasons


def main() -> None:
    print("=" * 112)
    print("ĐỐI CHIẾU 42 PHƯƠNG ÁN BẰNG MÃ TRƯỜNG QĐ3805 - TIỂU HỌC")
    print("Dự án:", PROJECT_DIR)
    print("Database:", DATABASE_PATH)
    print(
        "Chế độ: CHỈ ĐỌC - KHÔNG SỬA MÃ NGUỒN - "
        "KHÔNG GHI DATABASE - KHÔNG THỰC HIỆN SÁP NHẬP"
    )
    print("=" * 112)

    yid = school_year_id()
    preview = batch.build_level_batch_preview(
        school_year_id=yid,
        level_code=TARGET_LEVEL,
    )
    lock = load_lock()

    op_by_id = {
        str(x.get("operation_id") or ""): dict(x)
        for x in (lock.get("operations") or [])
    }

    schools = school_rows_for_level(yid, TARGET_LEVEL)

    by_code: dict[str, list[dict[str, Any]]] = {}
    for s in schools:
        code = str(s.get("code") or "").strip()
        if code:
            by_code.setdefault(code, []).append(s)

    rows = []
    seen_ops = set()

    for plan in preview.get("rows") or []:
        if str(plan.get("batch_state") or "").upper() != "BLOCK":
            continue
        if not has_name_problem(plan):
            continue

        op_id = str(plan.get("qd3805_operation_id") or "").strip()
        if not op_id or op_id in seen_ops:
            continue
        seen_ops.add(op_id)

        op = op_by_id.get(op_id)
        if not op:
            rows.append(
                {
                    "operation_id": op_id,
                    "commune": str(plan.get("commune_excel") or ""),
                    "plan_text": str(plan.get("plan_text") or ""),
                    "operation_classification": "KHONG_TIM_THAY_OPERATION_QD3805",
                    "schools": [],
                }
            )
            continue

        commune = str(op.get("commune") or plan.get("commune_excel") or "")
        member_results = []

        all_official_schools = list(op.get("source_schools") or [])

        for off in all_official_schools:
            codes = code_values(off)
            per_code = []
            for code in codes:
                matches = [dict(x) for x in by_code.get(code, [])]
                cls, reasons = classify_code_match(
                    off,
                    matches,
                    commune,
                )
                per_code.append(
                    {
                        "code": code,
                        "classification": cls,
                        "reasons": reasons,
                        "db_matches": [
                            {
                                "school_id": int(x.get("id")),
                                "code": str(x.get("code") or ""),
                                "name": str(x.get("name") or ""),
                                "commune": str(x.get("commune_name") or ""),
                                "is_active": bool(x.get("is_active")),
                            }
                            for x in matches
                        ],
                    }
                )

            if not codes:
                member_class = "QĐ3805_KHONG_CO_MA_TRUONG"
            elif all(
                x["classification"] == "KHOP_MA_TEN_DIA_BAN_DUY_NHAT"
                for x in per_code
            ):
                member_class = "AN_TOAN_TUYET_DOI"
            elif all(
                x["classification"] in {
                    "KHOP_MA_TEN_DIA_BAN_DUY_NHAT",
                    "KHOP_MA_CUNG_DIA_BAN_KHAC_TEN",
                    "KHOP_MA_TEN_DIA_BAN_NHUNG_INACTIVE",
                }
                for x in per_code
            ):
                member_class = "CO_THE_KHOA_BANG_MA_SAU_KHI_XAC_NHAN"
            else:
                member_class = "CAN_XU_LY"

            member_results.append(
                {
                    "official_name": str(off.get("name") or ""),
                    "codes": codes,
                    "levels": list(off.get("levels") or []),
                    "member_classification": member_class,
                    "code_results": per_code,
                }
            )

        target_codes = [
            str(x or "").strip()
            for x in (op.get("target_codes") or [])
            if str(x or "").strip()
        ]

        target_results = []
        for code in target_codes:
            target_results.append(
                {
                    "code": code,
                    "db_matches": [
                        {
                            "school_id": int(x.get("id")),
                            "code": str(x.get("code") or ""),
                            "name": str(x.get("name") or ""),
                            "commune": str(x.get("commune_name") or ""),
                            "is_active": bool(x.get("is_active")),
                        }
                        for x in by_code.get(code, [])
                    ],
                }
            )

        if member_results and all(
            x["member_classification"] == "AN_TOAN_TUYET_DOI"
            for x in member_results
        ):
            op_cls = "AN_TOAN_TUYET_DOI"
        elif member_results and all(
            x["member_classification"]
            in {
                "AN_TOAN_TUYET_DOI",
                "CO_THE_KHOA_BANG_MA_SAU_KHI_XAC_NHAN",
            }
            for x in member_results
        ):
            op_cls = "CO_THE_KHOA_BANG_MA"
        else:
            op_cls = "CAN_XU_LY"

        rows.append(
            {
                "operation_id": op_id,
                "commune": commune,
                "official_plan": str(op.get("official_plan") or ""),
                "target_text": str(op.get("target_text") or ""),
                "target_codes": target_codes,
                "target_results": target_results,
                "operation_classification": op_cls,
                "schools": member_results,
                "current_blockers": [
                    str(x) for x in (plan.get("batch_blockers") or [])
                ],
            }
        )

    counts = Counter(
        x["operation_classification"] for x in rows
    )

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_dir": str(PROJECT_DIR),
        "database_path": str(DATABASE_PATH),
        "database_sha256": (
            sha256_file(Path(DATABASE_PATH))
            if Path(DATABASE_PATH).exists()
            else None
        ),
        "school_year": TARGET_YEAR,
        "level_code": TARGET_LEVEL,
        "summary": {
            "operations_checked": len(rows),
            "classification_counts": dict(sorted(counts.items())),
            "effective_block_count_before": int(
                preview.get("effective_block_count") or 0
            ),
            "qd3805_expected_actions": int(
                preview.get("registry_action_expected_count") or 0
            ),
            "qd3805_mapped_actions": int(
                preview.get("registry_action_mapped_count") or 0
            ),
        },
        "rows": rows,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = (
        OUT_DIR
        / f"doi_chieu_42_bang_ma_truong_QD3805_{stamp}.json"
    )
    txt_path = (
        OUT_DIR
        / f"tom_tat_42_bang_ma_truong_QD3805_{stamp}.txt"
    )

    json_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    lines = [
        "ĐỐI CHIẾU 42 PHƯƠNG ÁN BẰNG MÃ TRƯỜNG QĐ3805 - TIỂU HỌC",
        "=" * 100,
        f"Tổng operation kiểm tra: {len(rows)}",
    ]
    for k, v in sorted(
        counts.items(),
        key=lambda z: (-z[1], z[0]),
    ):
        lines.append(f"{k}: {v}")

    lines.append("")
    lines.append("CHI TIẾT:")
    for row in rows:
        lines.append("-" * 100)
        lines.append(
            f"{row['operation_id']} | {row['commune']} | "
            f"{row['official_plan']} | "
            f"{row['operation_classification']}"
        )
        lines.append(
            "Đích QĐ3805: "
            + row["target_text"]
            + " | mã="
            + ",".join(row["target_codes"])
        )
        for school in row["schools"]:
            lines.append(
                f"  Nguồn: {school['official_name']} | "
                f"mã={','.join(school['codes'])} | "
                f"{school['member_classification']}"
            )
            for cr in school["code_results"]:
                for db in cr["db_matches"]:
                    lines.append(
                        f"    -> DB: {db['name']} | "
                        f"mã={db['code']} | "
                        f"school_id={db['school_id']} | "
                        f"xã={db['commune']} | "
                        f"active={db['is_active']} | "
                        f"{cr['classification']}"
                    )
                for reason in cr["reasons"]:
                    lines.append("       Lưu ý: " + reason)

    txt_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(f"Tổng operation kiểm tra: {len(rows)}")
    for k, v in sorted(
        counts.items(),
        key=lambda z: (-z[1], z[0]),
    ):
        print(f"{k}: {v}")

    print("-" * 112)
    print("Database: KHÔNG THAY ĐỔI")
    print("Báo cáo JSON:", json_path)
    print("Tóm tắt TXT:", txt_path)
    print("=" * 112)


if __name__ == "__main__":
    main()
