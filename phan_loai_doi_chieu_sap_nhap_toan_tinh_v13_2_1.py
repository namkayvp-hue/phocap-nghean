# -*- coding: utf-8 -*-
r"""
V13.2.1 - PHÂN LOẠI + ĐỐI CHIẾU NGUỒN SÁP NHẬP TOÀN TỈNH
========================================================

MỤC TIÊU
--------
Tự dò file Excel nguồn sáp nhập, phân nhóm toàn bộ phương án và đối chiếu
với database C:\PhoCap\data\phocap.db.

CHỈ ĐỌC:
- Không sửa database.
- Không sửa mã nguồn.
- Không thực hiện sáp nhập.
- Không đổi tên trường.

KẾT QUẢ
-------
Tạo 1 ZIP duy nhất gồm:
  00_TONG_QUAN_V13_2_1.txt
  700_DANH_SACH_NHOM_PHUONG_AN.csv
  701_SAP_NHAP_DON_GIAN_CO_THE_TU_DONG.csv
  702_NHOM_PHUC_TAP_CAN_ENGINE_MO_RONG.csv
  703_TRUONG_KHONG_KHOP_DATABASE.csv
  704_TRUONG_KHOP_NHIEU_DATABASE.csv
  705_DON_VI_KHONG_KHOP_DATABASE.csv
  706_DON_VI_KHOP_NHIEU_DATABASE.csv
  707_CAU_TRUC_NGUON_CAN_XEM.csv
  708_GATE_V13_2_1.csv

PHÂN LOẠI NGHIỆP VỤ
-------------------
- KEEP
- MERGE_EXISTING_TARGET
- MERGE_TO_NEW_NAME
- SPLIT
- TRANSFER_EXTERNAL
- SITE_TRANSFER
- REVIEW_OTHER

Chỉ MERGE_EXISTING_TARGET với tất cả school_id khớp duy nhất mới được đánh dấu
SAFE_FOR_BATCH_IMPORT=YES.

CHẠY
----
cd C:\PhoCap
.\.venv\Scripts\python.exe .\phan_loai_doi_chieu_sap_nhap_toan_tinh_v13_2_1.py
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
from typing import Any


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"

SOURCE_DIRS = [
    ROOT / "uploads",
    ROOT,
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Documents",
]

PREFERRED_NAMES = {
    "nguon sap nhap.xlsx",
    "nguồn sáp nhập.xlsx",
    "sap nhap.xlsx",
    "sáp nhập.xlsx",
}

EXPECTED_SOURCE_ROWS = 1284
EXPECTED_COMMUNE_COUNT = 131
EXPECTED_GROUPS = 656


class AuditStop(RuntimeError):
    pass


def clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def norm(value: Any) -> str:
    s = clean(value).lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(
        ch for ch in s
        if unicodedata.category(ch) != "Mn"
    )
    s = s.replace("đ", "d")
    s = s.replace("&", " va ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def norm_commune(value: Any) -> str:
    s = norm(value)
    for prefix in (
        "xa ",
        "phuong ",
        "thi tran ",
    ):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s.strip()


def norm_school(value: Any) -> str:
    s = norm(value)

    if s.startswith("truong "):
        s = s[7:].strip()

    replacements = [
        (r"\bmn\b", "mam non"),
        (r"\bthcs\b", "thcs"),
        (r"\bpt dtbt\b", "ptdtbt"),
        (r"\bptdt bt\b", "ptdtbt"),
        (r"\bpt dt bt\b", "ptdtbt"),
        (r"\bptdtbt\b", "ptdtbt"),
        (r"\bptcs\b", "pho thong co so"),
        (r"\btt\b", "thi tran"),
    ]

    for pattern, repl in replacements:
        s = re.sub(pattern, repl, s)

    # "TH ..." trong nguồn thường là Tiểu học.
    if s.startswith("th ") and not s.startswith("th thcs"):
        s = "tieu hoc " + s[3:]

    s = re.sub(r"\btieu hoc va thcs\b", "th va thcs", s)
    s = re.sub(r"\btieu hoc thcs\b", "th va thcs", s)
    s = re.sub(r"\bth thcs\b", "th va thcs", s)

    return " ".join(s.split())


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=headers,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _looks_like_merger_source(path: Path) -> tuple[bool, dict]:
    """
    Nhận diện file nguồn bằng cấu trúc thay vì tên file.
    Không đọc toàn bộ workbook nếu không cần.
    """
    try:
        from openpyxl import load_workbook
    except Exception as exc:
        raise AuditStop(f"Không import được openpyxl: {exc}")

    try:
        wb = load_workbook(
            path,
            read_only=True,
            data_only=True,
        )
    except Exception:
        return False, {}

    try:
        ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb[wb.sheetnames[0]]

        detected_rows = 0
        plan_rows = 0
        school_rows = 0
        commune_rows = 0

        # Nguồn chuẩn bắt đầu dữ liệu từ dòng 7.
        for values in ws.iter_rows(
            min_row=7,
            max_row=min(ws.max_row or 2000, 2200),
            values_only=True,
        ):
            if not values or len(values) < 6:
                continue

            commune = clean(values[1])
            school = clean(values[3])
            plan = clean(values[5])

            if school:
                school_rows += 1
                detected_rows += 1
            if commune:
                commune_rows += 1
            if plan:
                plan_rows += 1

        # Dấu hiệu đủ mạnh của file phương án toàn tỉnh.
        ok = (
            school_rows >= 100
            and plan_rows >= 50
            and commune_rows >= 20
        )

        return ok, {
            "school_rows": school_rows,
            "plan_rows": plan_rows,
            "commune_rows": commune_rows,
            "sheet": ws.title,
        }

    finally:
        wb.close()


def locate_source() -> Path:
    candidates: list[tuple[Path, dict]] = []
    seen: set[Path] = set()

    # Ưu tiên tên quen thuộc trước.
    for folder in SOURCE_DIRS:
        if not folder.exists() or not folder.is_dir():
            continue

        try:
            items = list(folder.glob("*.xlsx"))
        except Exception:
            continue

        for path in items:
            try:
                resolved = path.resolve()
            except Exception:
                resolved = path

            if resolved in seen:
                continue
            seen.add(resolved)

            low = path.name.lower().strip()
            if low.startswith("~$"):
                continue

            ok, info = _looks_like_merger_source(path)
            if ok:
                info["preferred_name"] = (
                    norm(path.name) in {
                        norm(x) for x in PREFERRED_NAMES
                    }
                )
                candidates.append((path, info))

    if not candidates:
        found = []
        for folder in SOURCE_DIRS:
            if folder.exists() and folder.is_dir():
                try:
                    found.extend(
                        str(p)
                        for p in folder.glob("*.xlsx")
                        if not p.name.startswith("~$")
                    )
                except Exception:
                    pass

        raise AuditStop(
            "Không tự nhận diện được file nguồn sáp nhập trong các thư mục đã quét.\\n"
            "Các thư mục đã quét:\\n- "
            + "\\n- ".join(str(x) for x in SOURCE_DIRS)
            + "\\n\\nCác file .xlsx đang thấy:\\n- "
            + ("\\n- ".join(found) if found else "(không có)")
            + "\\n\\nCách nhanh nhất: chép file nguồn vào C:\\\\PhoCap\\\\uploads rồi chạy lại."
        )

    # Ưu tiên file có số dòng gần nguồn chuẩn 1284 nhất,
    # sau đó ưu tiên tên quen thuộc.
    candidates.sort(
        key=lambda item: (
            abs(int(item[1]["school_rows"]) - EXPECTED_SOURCE_ROWS),
            0 if item[1].get("preferred_name") else 1,
            str(item[0]).lower(),
        )
    )

    best_path, best_info = candidates[0]

    # Nếu có nhiều file có độ phù hợp gần như nhau, dừng và liệt kê để tránh chọn nhầm.
    tied = [
        (p, info)
        for p, info in candidates
        if abs(int(info["school_rows"]) - EXPECTED_SOURCE_ROWS)
        == abs(int(best_info["school_rows"]) - EXPECTED_SOURCE_ROWS)
    ]

    if len(tied) > 1:
        raise AuditStop(
            "Tìm thấy nhiều file Excel có cấu trúc nguồn sáp nhập tương đương. "
            "Chưa tự chọn để tránh nhầm:\\n- "
            + "\\n- ".join(
                f"{p} | school_rows={info['school_rows']} | "
                f"plan_rows={info['plan_rows']} | sheet={info['sheet']}"
                for p, info in tied
            )
            + "\\n\\nHãy chép file đúng vào C:\\\\PhoCap\\\\uploads và đổi tên thành "
              "'Nguồn sáp nhập.xlsx', rồi chạy lại."
        )

    print(
        "Tự nhận diện file nguồn: "
        f"{best_path} | school_rows={best_info['school_rows']} | "
        f"plan_rows={best_info['plan_rows']} | sheet={best_info['sheet']}"
    )
    return best_path


def read_source(path: Path) -> list[dict]:
    try:
        from openpyxl import load_workbook
    except Exception as exc:
        raise AuditStop(
            f"Không import được openpyxl: {exc}"
        )

    wb = load_workbook(
        path,
        read_only=True,
        data_only=True,
    )

    try:
        ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb[wb.sheetnames[0]]

        rows = []
        current_commune = ""

        for excel_row, values in enumerate(
            ws.iter_rows(
                min_row=7,
                values_only=True,
            ),
            start=7,
        ):
            if len(values) < 6:
                continue

            stt = values[0]
            commune = clean(values[1])
            area = clean(values[2])
            school = clean(values[3])
            class_count = values[4]
            plan = clean(values[5])
            note = clean(values[6]) if len(values) > 6 else ""

            if commune:
                current_commune = commune

            if not school:
                continue

            rows.append({
                "excel_row": excel_row,
                "stt": stt,
                "commune": current_commune,
                "area": area,
                "school": school,
                "class_count": class_count,
                "plan": plan,
                "note": note,
            })

        return rows

    finally:
        wb.close()


def build_groups(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    groups = []
    structural = []

    last_commune = None
    current_group = None
    group_no = 0

    for row in rows:
        commune = row["commune"]

        if commune != last_commune:
            current_group = None
            last_commune = commune

        plan = row["plan"]

        if plan:
            group_no += 1

            if norm(plan) == "giu nguyen":
                group = {
                    "group_no": group_no,
                    "commune": commune,
                    "plan": "Giữ nguyên",
                    "target_text": row["school"],
                    "members": [row],
                    "keep": True,
                }
                groups.append(group)
                current_group = None
            else:
                group = {
                    "group_no": group_no,
                    "commune": commune,
                    "plan": plan,
                    "target_text": plan,
                    "members": [row],
                    "keep": False,
                }
                groups.append(group)
                current_group = group

        else:
            if current_group is None:
                structural.append({
                    **row,
                    "issue": (
                        "Dòng không có Phương án sắp xếp và không nằm sau "
                        "một nhóm đích trong cùng xã/đơn vị."
                    ),
                })
            else:
                current_group["members"].append(row)

    return groups, structural


def classify(group: dict) -> str:
    if group["keep"]:
        return "KEEP"

    p = norm(group["plan"])
    target = norm_school(group["target_text"])
    members = [
        norm_school(x["school"])
        for x in group["members"]
    ]

    if p.startswith("tach ") or " tach " in (" " + p + " "):
        return "SPLIT"

    if (
        "tiep nhan diem" in p
        or "tiep nhap diem" in p
        or "diem le" in p
        or "diem truong" in p
    ):
        return "SITE_TRANSFER"

    if (
        "sap nhap vao thpt" in p
        or (
            len(group["members"]) == 1
            and "thpt " in p
            and target not in members
        )
    ):
        return "TRANSFER_EXTERNAL"

    if target in members:
        if len(group["members"]) >= 2:
            return "MERGE_EXISTING_TARGET"
        return "KEEP"

    if len(group["members"]) >= 2:
        return "MERGE_TO_NEW_NAME"

    return "REVIEW_OTHER"


def connect_ro() -> sqlite3.Connection:
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(
        uri,
        uri=True,
        timeout=30,
    )
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def table_cols(con, table: str) -> set[str]:
    return {
        str(r[1])
        for r in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    }


def load_db(con: sqlite3.Connection):
    school_cols = table_cols(con, "schools")
    commune_cols = table_cols(con, "communes")

    school_name_col = next(
        (
            c for c in (
                "name",
                "school_name",
                "ten_truong",
            )
            if c in school_cols
        ),
        None,
    )

    commune_name_col = next(
        (
            c for c in (
                "name",
                "commune_name",
                "ten_xa",
            )
            if c in commune_cols
        ),
        None,
    )

    if not school_name_col or not commune_name_col:
        raise AuditStop(
            "Không xác định được cột tên schools/communes."
        )

    school_code_col = next(
        (
            c for c in (
                "code",
                "school_code",
                "ma_truong",
            )
            if c in school_cols
        ),
        None,
    )

    school_level_col = next(
        (
            c for c in (
                "level",
                "education_level",
                "school_level",
            )
            if c in school_cols
        ),
        None,
    )

    school_select = [
        "s.id AS id",
        f"s.{qident(school_name_col)} AS name",
        "s.commune_id AS commune_id",
        (
            f"s.{qident(school_code_col)} AS code"
            if school_code_col
            else "'' AS code"
        ),
        (
            f"s.{qident(school_level_col)} AS level"
            if school_level_col
            else "'' AS level"
        ),
        (
            "s.is_active AS is_active"
            if "is_active" in school_cols
            else "NULL AS is_active"
        ),
        f"c.{qident(commune_name_col)} AS commune_name",
    ]

    school_rows = con.execute(
        "SELECT "
        + ",".join(school_select)
        + " FROM schools s "
          "LEFT JOIN communes c ON c.id=s.commune_id "
          "ORDER BY s.id"
    ).fetchall()

    commune_rows = con.execute(
        "SELECT id,"
        + qident(commune_name_col)
        + " AS name "
          "FROM communes ORDER BY id"
    ).fetchall()

    schools = [dict(r) for r in school_rows]
    communes = [dict(r) for r in commune_rows]

    return schools, communes


def commune_matches(
    source_name: str,
    communes: list[dict],
) -> list[dict]:
    key = norm_commune(source_name)

    exact = [
        x for x in communes
        if norm_commune(x["name"]) == key
    ]

    return exact


def school_matches(
    source_name: str,
    commune_id: int,
    schools: list[dict],
) -> list[dict]:
    key = norm_school(source_name)

    candidates = [
        x for x in schools
        if int(x["commune_id"] or 0) == int(commune_id)
    ]

    exact = [
        x for x in candidates
        if norm_school(x["name"]) == key
    ]

    if exact:
        return exact

    # Fallback nhẹ: bỏ "thi tran" trong tên trường.
    def lighter(value: str) -> str:
        return re.sub(
            r"\bthi tran\b",
            "",
            norm_school(value),
        ).strip()

    light_key = lighter(source_name)
    light = [
        x for x in candidates
        if lighter(x["name"]) == light_key
    ]

    return light


def main() -> int:
    print("=" * 126)
    print("V13.2 - PHÂN LOẠI + ĐỐI CHIẾU SÁP NHẬP TOÀN TỈNH")
    print("=" * 126)
    print("CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not DB_PATH.exists():
        raise AuditStop(
            f"Không tìm thấy database: {DB_PATH}"
        )

    source = locate_source()
    print(f"Nguồn: {source}")

    rows = read_source(source)
    groups, structural = build_groups(rows)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"bao_cao_v13_2_1_sap_nhap_toan_tinh_{stamp}"
    zip_path = ROOT / f"bao_cao_v13_2_1_sap_nhap_toan_tinh_{stamp}.zip"
    out_dir.mkdir(parents=True, exist_ok=False)

    con = connect_ro()

    try:
        integrity = con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        fk = con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        schools, communes = load_db(con)

        commune_cache = {}
        unmatched_communes = []
        ambiguous_communes = []

        for name in sorted({x["commune"] for x in rows}):
            matches = commune_matches(
                name,
                communes,
            )
            commune_cache[name] = matches

            if len(matches) == 0:
                unmatched_communes.append({
                    "source_commune": name,
                    "normalized": norm_commune(name),
                })
            elif len(matches) > 1:
                ambiguous_communes.append({
                    "source_commune": name,
                    "normalized": norm_commune(name),
                    "matches": " | ".join(
                        f"{x['id']}:{x['name']}"
                        for x in matches
                    ),
                })

        unmatched_schools = []
        ambiguous_schools = []
        group_rows = []
        safe_rows = []
        complex_rows = []

        class_counter = Counter()
        safe_count = 0

        for group in groups:
            op = classify(group)
            class_counter[op] += 1

            commune_matches_rows = commune_cache.get(
                group["commune"],
                [],
            )

            commune_id = (
                int(commune_matches_rows[0]["id"])
                if len(commune_matches_rows) == 1
                else None
            )

            member_results = []
            all_members_unique = True

            for member in group["members"]:
                matches = (
                    school_matches(
                        member["school"],
                        commune_id,
                        schools,
                    )
                    if commune_id is not None
                    else []
                )

                if len(matches) == 1:
                    matched = matches[0]
                    member_results.append({
                        **member,
                        "school_id": int(matched["id"]),
                        "db_name": matched["name"],
                        "school_code": matched.get("code"),
                        "school_level": matched.get("level"),
                        "is_active": matched.get("is_active"),
                        "match_count": 1,
                    })
                else:
                    all_members_unique = False

                    member_results.append({
                        **member,
                        "school_id": None,
                        "db_name": "",
                        "school_code": "",
                        "school_level": "",
                        "is_active": None,
                        "match_count": len(matches),
                    })

                    if len(matches) == 0:
                        unmatched_schools.append({
                            "group_no": group["group_no"],
                            "source_commune": group["commune"],
                            "source_school": member["school"],
                            "plan": group["plan"],
                            "normalized_school": norm_school(
                                member["school"]
                            ),
                        })
                    else:
                        ambiguous_schools.append({
                            "group_no": group["group_no"],
                            "source_commune": group["commune"],
                            "source_school": member["school"],
                            "plan": group["plan"],
                            "matches": " | ".join(
                                f"{x['id']}:{x['name']}"
                                for x in matches
                            ),
                        })

            target_member = None
            target_norm = norm_school(
                group["target_text"]
            )

            for item in member_results:
                if (
                    item["school_id"] is not None
                    and norm_school(item["school"]) == target_norm
                ):
                    target_member = item
                    break

            safe = (
                op == "MERGE_EXISTING_TARGET"
                and commune_id is not None
                and all_members_unique
                and target_member is not None
                and len(member_results) >= 2
            )

            if safe:
                safe_count += 1

            member_text = " | ".join(
                (
                    f"{x['school']}"
                    + (
                        f" [id={x['school_id']}]"
                        if x["school_id"] is not None
                        else " [KHÔNG KHỚP]"
                    )
                )
                for x in member_results
            )

            source_ids = [
                int(x["school_id"])
                for x in member_results
                if x["school_id"] is not None
                and (
                    target_member is None
                    or int(x["school_id"])
                    != int(target_member["school_id"])
                )
            ]

            row = {
                "group_no": group["group_no"],
                "commune": group["commune"],
                "commune_id": commune_id,
                "operation_type": op,
                "plan": group["plan"],
                "target_text": group["target_text"],
                "target_school_id": (
                    target_member["school_id"]
                    if target_member
                    else None
                ),
                "member_count": len(member_results),
                "source_school_ids": ",".join(
                    str(x) for x in source_ids
                ),
                "members": member_text,
                "all_members_unique_db_match": (
                    "YES" if all_members_unique else "NO"
                ),
                "SAFE_FOR_BATCH_IMPORT": (
                    "YES" if safe else "NO"
                ),
            }

            group_rows.append(row)

            if safe:
                safe_rows.append(row)
            elif op != "KEEP":
                complex_rows.append(row)

        gate_rows = [
            {
                "check": "database_integrity",
                "result": "PASS" if integrity == "ok" else "FAIL",
                "detail": str(integrity),
            },
            {
                "check": "database_foreign_key",
                "result": "PASS" if not fk else "FAIL",
                "detail": str(len(fk)),
            },
            {
                "check": "source_rows",
                "result": (
                    "PASS"
                    if len(rows) == EXPECTED_SOURCE_ROWS
                    else "REVIEW"
                ),
                "detail": str(len(rows)),
            },
            {
                "check": "source_communes",
                "result": (
                    "PASS"
                    if len({x['commune'] for x in rows})
                    == EXPECTED_COMMUNE_COUNT
                    else "REVIEW"
                ),
                "detail": str(
                    len({x["commune"] for x in rows})
                ),
            },
            {
                "check": "source_groups",
                "result": (
                    "PASS"
                    if len(groups) == EXPECTED_GROUPS
                    else "REVIEW"
                ),
                "detail": str(len(groups)),
            },
            {
                "check": "structural_source_rows",
                "result": (
                    "PASS" if not structural else "REVIEW"
                ),
                "detail": str(len(structural)),
            },
            {
                "check": "unmatched_communes",
                "result": (
                    "PASS"
                    if not unmatched_communes
                    else "REVIEW"
                ),
                "detail": str(len(unmatched_communes)),
            },
            {
                "check": "ambiguous_communes",
                "result": (
                    "PASS"
                    if not ambiguous_communes
                    else "REVIEW"
                ),
                "detail": str(len(ambiguous_communes)),
            },
            {
                "check": "unmatched_school_rows",
                "result": (
                    "PASS"
                    if not unmatched_schools
                    else "REVIEW"
                ),
                "detail": str(len(unmatched_schools)),
            },
            {
                "check": "ambiguous_school_rows",
                "result": (
                    "PASS"
                    if not ambiguous_schools
                    else "REVIEW"
                ),
                "detail": str(len(ambiguous_schools)),
            },
            {
                "check": "safe_simple_merger_groups",
                "result": "INFO",
                "detail": str(safe_count),
            },
        ]

        write_csv(
            out_dir / "700_DANH_SACH_NHOM_PHUONG_AN.csv",
            [
                "group_no",
                "commune",
                "commune_id",
                "operation_type",
                "plan",
                "target_text",
                "target_school_id",
                "member_count",
                "source_school_ids",
                "members",
                "all_members_unique_db_match",
                "SAFE_FOR_BATCH_IMPORT",
            ],
            group_rows,
        )

        write_csv(
            out_dir / "701_SAP_NHAP_DON_GIAN_CO_THE_TU_DONG.csv",
            [
                "group_no",
                "commune",
                "commune_id",
                "operation_type",
                "plan",
                "target_text",
                "target_school_id",
                "member_count",
                "source_school_ids",
                "members",
                "SAFE_FOR_BATCH_IMPORT",
            ],
            safe_rows,
        )

        write_csv(
            out_dir / "702_NHOM_PHUC_TAP_CAN_ENGINE_MO_RONG.csv",
            [
                "group_no",
                "commune",
                "commune_id",
                "operation_type",
                "plan",
                "target_text",
                "target_school_id",
                "member_count",
                "source_school_ids",
                "members",
                "all_members_unique_db_match",
            ],
            complex_rows,
        )

        write_csv(
            out_dir / "703_TRUONG_KHONG_KHOP_DATABASE.csv",
            [
                "group_no",
                "source_commune",
                "source_school",
                "plan",
                "normalized_school",
            ],
            unmatched_schools,
        )

        write_csv(
            out_dir / "704_TRUONG_KHOP_NHIEU_DATABASE.csv",
            [
                "group_no",
                "source_commune",
                "source_school",
                "plan",
                "matches",
            ],
            ambiguous_schools,
        )

        write_csv(
            out_dir / "705_DON_VI_KHONG_KHOP_DATABASE.csv",
            [
                "source_commune",
                "normalized",
            ],
            unmatched_communes,
        )

        write_csv(
            out_dir / "706_DON_VI_KHOP_NHIEU_DATABASE.csv",
            [
                "source_commune",
                "normalized",
                "matches",
            ],
            ambiguous_communes,
        )

        write_csv(
            out_dir / "707_CAU_TRUC_NGUON_CAN_XEM.csv",
            [
                "excel_row",
                "stt",
                "commune",
                "area",
                "school",
                "class_count",
                "plan",
                "note",
                "issue",
            ],
            structural,
        )

        write_csv(
            out_dir / "708_GATE_V13_2_1.csv",
            [
                "check",
                "result",
                "detail",
            ],
            gate_rows,
        )

        summary = out_dir / "00_TONG_QUAN_V13_2_1.txt"

        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "V13.2 - PHÂN LOẠI + ĐỐI CHIẾU SÁP NHẬP TOÀN TỈNH\n"
            )
            f.write("=" * 110 + "\n\n")
            f.write(f"Nguồn: {source}\n")
            f.write(f"Dòng trường: {len(rows)}\n")
            f.write(
                "Xã/đơn vị: "
                f"{len({x['commune'] for x in rows})}\n"
            )
            f.write(f"Nhóm phương án: {len(groups)}\n\n")

            f.write("PHÂN LOẠI NGHIỆP VỤ\n")
            for key, value in sorted(
                class_counter.items(),
                key=lambda x: (-x[1], x[0]),
            ):
                f.write(f"- {key}: {value}\n")

            f.write("\nĐỐI CHIẾU DATABASE\n")
            f.write(
                f"- safe simple merger groups: {safe_count}\n"
            )
            f.write(
                f"- unmatched communes: {len(unmatched_communes)}\n"
            )
            f.write(
                f"- ambiguous communes: {len(ambiguous_communes)}\n"
            )
            f.write(
                f"- unmatched school rows: {len(unmatched_schools)}\n"
            )
            f.write(
                f"- ambiguous school rows: {len(ambiguous_schools)}\n"
            )
            f.write(
                f"- structural source rows: {len(structural)}\n"
            )

            f.write("\nQUY TẮC BƯỚC SAU\n")
            f.write(
                "- Chỉ file 701 được phép đưa vào batch importer "
                "của engine V13 hiện tại.\n"
            )
            f.write(
                "- File 702 phải được chia tiếp theo nghiệp vụ: "
                "sáp nhập + đổi tên, lập trường liên cấp mới, "
                "tách cấp học, nhập THPT, chuyển điểm trường.\n"
            )
            f.write(
                "- Không thực hiện tự động bất kỳ nhóm nào có "
                "school/commune không khớp duy nhất DB.\n"
            )

        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 126)
        print("HOÀN THÀNH V13.2.1")
        print("=" * 126)
        print(f"Dòng trường nguồn: {len(rows)}")
        print(
            "Xã/đơn vị nguồn: "
            f"{len({x['commune'] for x in rows})}"
        )
        print(f"Nhóm phương án: {len(groups)}")
        print()
        print("Phân loại:")
        for key, value in sorted(
            class_counter.items(),
            key=lambda x: (-x[1], x[0]),
        ):
            print(f"  {key}: {value}")
        print()
        print(
            f"SAFE simple merger groups: {safe_count}"
        )
        print(
            f"Unmatched communes: {len(unmatched_communes)}"
        )
        print(
            f"Unmatched school rows: {len(unmatched_schools)}"
        )
        print(
            f"Ambiguous school rows: {len(ambiguous_schools)}"
        )
        print(
            f"Structural source rows: {len(structural)}"
        )
        print("Database: KHÔNG THAY ĐỔI")
        print(f"ZIP: {zip_path}")

        return 0

    finally:
        con.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditStop as exc:
        print()
        print("=" * 126)
        print("V13.2.1 DỪNG AN TOÀN")
        print("=" * 126)
        print(str(exc))
        print("Database: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
