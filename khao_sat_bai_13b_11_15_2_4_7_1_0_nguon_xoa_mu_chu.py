from __future__ import annotations

import ast
import os
import sqlite3
from collections import Counter
from datetime import date, datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"
SERVICE = APP / "services" / "xmc_report_v247.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = EXPORTS / f"khao_sat_nguon_xmc_bai_13b_11_15_2_4_7_1_0_{STAMP}.txt"


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def function_source(source: str, name: str) -> str:
    if not source:
        return ""
    tree = ast.parse(source)
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1:
        return f"[Không tìm thấy đúng 1 hàm {name}; hiện có {len(matches)}]"
    node = matches[0]
    lines = source.splitlines()
    return "\n".join(
        f"{i:5d}: {lines[i-1]}"
        for i in range(int(node.lineno), int(node.end_lineno) + 1)
    )


def norm_bool(value):
    if value is None:
        return None
    return bool(int(value))


def birth_year(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).year
        except ValueError:
            pass
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def bool_label(value):
    if value is True:
        return "Có"
    if value is False:
        return "Không"
    return "Chưa xác định"


def cohort(age):
    if age is None:
        return None
    if 15 <= age <= 25:
        return "15-25"
    if 26 <= age <= 35:
        return "26-35"
    if 36 <= age <= 60:
        return "36-60"
    return None


def main():
    print("=" * 118)
    print("BÀI 13B-11.15.2.4.7.1-0 - KHẢO SÁT NGUỒN DỮ LIỆU XÓA MÙ CHỮ")
    print("=" * 118)
    print("CHỈ ĐỌC source + database; KHÔNG sửa gì.")
    print()

    if not DB.exists():
        raise SystemExit(f"Không tìm thấy database: {DB}")

    builder_text = read_text(BUILDERS)
    if not builder_text:
        raise SystemExit(f"Không tìm thấy source: {BUILDERS}")

    ast.parse(builder_text)

    service_text = read_text(SERVICE)
    if service_text:
        ast.parse(service_text)

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(conn.execute("PRAGMA foreign_key_check").fetchall())

        if integrity != "ok":
            raise RuntimeError(f"integrity_check={integrity}")
        if fk_count != 0:
            raise RuntimeError(f"foreign_key_check={fk_count}")

        cols = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }
        required = {
            "is_literacy_target",
            "literacy_status",
            "completed_grade_3",
            "completed_grade_5",
        }
        missing = required - cols
        if missing:
            raise RuntimeError(
                "Thiếu cột XMC: " + ", ".join(sorted(missing))
            )

        years = conn.execute(
            """
            SELECT id, code, name
            FROM school_years
            ORDER BY id DESC
            """
        ).fetchall()

        chosen = None
        for row in years:
            code = str(row["code"] or "")
            if "2026" in code and "2027" in code:
                chosen = row
                break

        if chosen is None and years:
            chosen = years[0]

        if chosen is None:
            raise RuntimeError("Không có năm học trong database.")

        year_id = int(chosen["id"])
        year_code = str(chosen["code"] or chosen["name"] or year_id)

        # Năm tham chiếu đang dùng trong các builder hiện tại:
        # ảnh xuất 2026-2027 cho 15 tuổi -> năm sinh 2011, tức reference_year=2026.
        digits = [int(x) for x in year_code.replace("/", "-").split("-") if x.isdigit()]
        ref_year = digits[0] if digits else datetime.now().year

        rows = conn.execute(
            """
            SELECT
                sp.id AS person_id,
                sp.code AS person_code,
                sp.full_name,
                sp.date_of_birth,
                sp.gender,
                sp.ethnic_group,
                spr.id AS year_record_id,
                spr.is_literacy_target,
                spr.literacy_status,
                spr.completed_grade_3,
                spr.completed_grade_5,
                spr.learning_status,
                spr.school_name_reported,
                spr.class_name_reported
            FROM survey_people AS sp
            LEFT JOIN survey_person_year_records AS spr
              ON spr.survey_person_id = sp.id
             AND spr.school_year_id = ?
            WHERE COALESCE(sp.is_active, 1) = 1
            ORDER BY sp.id
            """,
            (year_id,),
        ).fetchall()

        # Nếu có nhiều year-record cho cùng người, ưu tiên record id lớn nhất.
        dedup = {}
        for row in rows:
            pid = int(row["person_id"])
            current = dedup.get(pid)
            if current is None:
                dedup[pid] = row
            else:
                old_id = current["year_record_id"] or -1
                new_id = row["year_record_id"] or -1
                if new_id > old_id:
                    dedup[pid] = row

        items = []
        for row in dedup.values():
            by = birth_year(row["date_of_birth"])
            age = ref_year - by if by is not None else None
            if age is None or age < 15 or age > 60:
                continue

            items.append(
                {
                    "person_id": int(row["person_id"]),
                    "code": str(row["person_code"] or ""),
                    "name": str(row["full_name"] or ""),
                    "age": age,
                    "birth_year": by,
                    "gender": str(row["gender"] or ""),
                    "ethnic": str(row["ethnic_group"] or ""),
                    "record_id": row["year_record_id"],
                    "target": norm_bool(row["is_literacy_target"]),
                    "status": str(row["literacy_status"] or ""),
                    "g3": norm_bool(row["completed_grade_3"]),
                    "g5": norm_bool(row["completed_grade_5"]),
                    "learning": str(row["learning_status"] or ""),
                }
            )

        groups = {
            "15-25": [x for x in items if 15 <= x["age"] <= 25],
            "15-35": [x for x in items if 15 <= x["age"] <= 35],
            "15-60": [x for x in items if 15 <= x["age"] <= 60],
            "26-35": [x for x in items if 26 <= x["age"] <= 35],
            "36-60": [x for x in items if 36 <= x["age"] <= 60],
        }

        lines = []
        lines.append("=" * 118 + "\n")
        lines.append("BÀI 13B-11.15.2.4.7.1-0 - KHẢO SÁT NGUỒN XÓA MÙ CHỮ\n")
        lines.append("=" * 118 + "\n\n")
        lines.append(f"Project: {PROJECT}\n")
        lines.append(f"Database: {DB}\n")
        lines.append(f"Năm học chọn: {year_code} (id={year_id})\n")
        lines.append(f"Năm tham chiếu: {ref_year}\n")
        lines.append(f"integrity_check: {integrity}\n")
        lines.append(f"foreign_key_check: {fk_count} lỗi\n\n")

        lines.append("I. KẾT QUẢ DÂN SỐ 15-60\n")
        lines.append("-" * 118 + "\n")
        for key in ("15-25", "26-35", "15-35", "36-60", "15-60"):
            lines.append(f" - {key}: {len(groups[key])} người\n")
        lines.append("\n")

        lines.append("II. ĐỘ PHỦ 4 FIELD XMC TRONG DATABASE\n")
        lines.append("-" * 118 + "\n")
        for key in ("15-25", "15-35", "15-60"):
            group = groups[key]
            lines.append(f"\n[{key}] Tổng {len(group)}\n")
            for field in ("target", "g3", "g5"):
                c = Counter(x[field] for x in group)
                lines.append(
                    f" - {field}: Có={c.get(True,0)} | "
                    f"Không={c.get(False,0)} | "
                    f"Chưa xác định={c.get(None,0)}\n"
                )
            status = Counter((x["status"] or "TRỐNG") for x in group)
            lines.append(" - literacy_status:\n")
            for value, count in sorted(status.items()):
                lines.append(f"    • {value}: {count}\n")

        lines.append("\nIII. ỨNG VIÊN NGUỒN THEO Ý NGHĨA UI ĐÃ CÓ\n")
        lines.append("-" * 118 + "\n")
        lines.append(
            "Đây CHỈ LÀ đối chiếu số lượng, CHƯA sửa report:\n"
        )
        lines.append(
            " - Mù chữ mức 1 ứng viên: completed_grade_3 = Không.\n"
        )
        lines.append(
            " - Biết chữ mức 1 ứng viên: completed_grade_3 = Có.\n"
        )
        lines.append(
            " - Mù chữ mức 2 ứng viên: completed_grade_5 = Không.\n"
        )
        lines.append(
            " - Biết chữ mức 2 ứng viên: completed_grade_5 = Có.\n"
        )
        lines.append(
            " - literacy_status/is_literacy_target được in riêng để kiểm tra "
            "có cần dùng làm điều kiện lọc hay không.\n\n"
        )

        for key in ("15-25", "15-35", "15-60"):
            group = groups[key]
            lines.append(f"[{key}]\n")
            lines.append(
                f" - completed_grade_3=False (MC mức 1 ứng viên): "
                f"{sum(x['g3'] is False for x in group)}\n"
            )
            lines.append(
                f" - completed_grade_3=True (Biết chữ mức 1 ứng viên): "
                f"{sum(x['g3'] is True for x in group)}\n"
            )
            lines.append(
                f" - completed_grade_5=False (MC mức 2 ứng viên): "
                f"{sum(x['g5'] is False for x in group)}\n"
            )
            lines.append(
                f" - completed_grade_5=True (Biết chữ mức 2 ứng viên): "
                f"{sum(x['g5'] is True for x in group)}\n"
            )
            lines.append("\n")

        lines.append("IV. CHI TIẾT TỪNG NGƯỜI 15-60\n")
        lines.append("-" * 118 + "\n")
        lines.append(
            "ID | Mã | Tuổi | Năm sinh | Họ tên | XMC? | Trạng thái XMC | "
            "HT lớp 3 | HT lớp 5 | Tình trạng học\n"
        )
        for x in sorted(items, key=lambda a: (a["age"], a["person_id"])):
            lines.append(
                f"{x['person_id']} | {x['code']} | {x['age']} | {x['birth_year']} | "
                f"{x['name']} | {bool_label(x['target'])} | "
                f"{x['status'] or 'TRỐNG'} | {bool_label(x['g3'])} | "
                f"{bool_label(x['g5'])} | {x['learning'] or 'TRỐNG'}\n"
            )

        lines.append("\nV. SOURCE REPORT HIỆN TẠI\n")
        lines.append("-" * 118 + "\n")
        for name in (
            "_population_metrics",
            "_build_xmc3",
            "_build_cmc2",
            "_build_cmc1",
            "_build_xmc4",
        ):
            lines.append(f"\n### {name}\n")
            lines.append(function_source(builder_text, name))
            lines.append("\n")

        lines.append("\nVI. BÀI 4.7 - BỘ TÍNH TỶ LỆ\n")
        lines.append("-" * 118 + "\n")
        if not service_text:
            lines.append("Không tìm thấy app/services/xmc_report_v247.py\n")
        else:
            for token in (
                "CMC1_PERCENT_FORMULAS",
                "XMC3_PERCENT_FORMULAS",
                "XMC4_PERCENT_FORMULAS",
                "apply_xmc_formula_contract",
            ):
                lines.append(
                    f" - {token}: {'CÓ' if token in service_text else 'KHÔNG'}\n"
                )

        lines.append("\nVII. KẾT LUẬN TỰ ĐỘNG\n")
        lines.append("-" * 118 + "\n")
        g3_known = sum(x["g3"] is not None for x in items)
        g5_known = sum(x["g5"] is not None for x in items)
        status_known = sum(bool(x["status"]) and x["status"] != "CHUA_XAC_DINH" for x in items)
        target_known = sum(x["target"] is not None for x in items)

        lines.append(f" - Số người 15-60: {len(items)}\n")
        lines.append(f" - Có dữ liệu completed_grade_3: {g3_known}/{len(items)}\n")
        lines.append(f" - Có dữ liệu completed_grade_5: {g5_known}/{len(items)}\n")
        lines.append(f" - Có dữ liệu is_literacy_target: {target_known}/{len(items)}\n")
        lines.append(f" - literacy_status khác trống/chưa xác định: {status_known}/{len(items)}\n")

        if g3_known == 0 and g5_known == 0:
            lines.append(
                " => CHƯA THỂ nối báo cáo an toàn: dữ liệu lớp 3/lớp 5 chưa được nhập.\n"
            )
        elif g3_known < len(items) or g5_known < len(items):
            lines.append(
                " => CÓ nguồn nhưng CHƯA ĐỦ: cần xác định quy tắc xử lý bản ghi chưa xác định.\n"
            )
        else:
            lines.append(
                " => Nguồn completed_grade_3/5 đã phủ đủ 15-60; có thể làm Bài 4.7.1 nối report.\n"
            )

        lines.append(
            "\nSource/database: KHÔNG THAY ĐỔI.\n"
        )

        EXPORTS.mkdir(parents=True, exist_ok=True)
        OUT.write_text("".join(lines), encoding="utf-8")

    finally:
        conn.close()

    print("KHẢO SÁT THÀNH CÔNG")
    print("Source/database: KHÔNG THAY ĐỔI")
    print("Báo cáo:", OUT)


if __name__ == "__main__":
    main()
