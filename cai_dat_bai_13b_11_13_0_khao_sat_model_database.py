from __future__ import annotations

import ast
import os
import re
import sqlite3
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
DB_PATH = PROJECT / "data" / "phocap.db"
EXPORT_DIR = PROJECT / "exports"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORT_DIR / f"khao_sat_bai_13b_11_13_0_{STAMP}.txt"

TARGET_TABLES = [
    "survey_person_year_records",
    "survey_people",
    "survey_forms",
    "households",
]

TARGET_CLASSES = {
    "SurveyPersonYearRecord",
    "SurveyPerson",
    "SurveyForm",
    "Household",
}

KEYWORDS = {
    "XMC": ["xoa_mu", "literacy", "mu_chu", "illiter"],
    "LOP_3": ["lop_3", "grade_3", "grade3", "completed_grade_3"],
    "LOP_5": ["lop_5", "grade_5", "grade5", "completed_grade_5"],
    "TIEU_HOC": ["tieu_hoc", "primary", "completed_primary"],
    "THCS": ["thcs", "lower_secondary", "completed_lower_secondary"],
    "KHUYET_TAT": ["khuyet_tat", "disability", "disabled"],
    "MAM_NON": ["mam_non", "gdmn", "preschool", "mau_giao"],
    "TINH_TRANG_HOC": ["tinh_trang_hoc", "learning_status", "study_status"],
    "TRUONG_LOP": ["school_id", "class_id", "school_name", "class_name"],
}

TEXT_EXTENSIONS = {".py", ".html", ".htm", ".js", ".json", ".txt"}


def add(out: list[str], text: str = "") -> None:
    out.append(text)


def section(out: list[str], title: str) -> None:
    add(out)
    add(out, "=" * 112)
    add(out, title)
    add(out, "=" * 112)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def inspect_database(out: list[str]) -> dict[str, list[tuple]]:
    info: dict[str, list[tuple]] = {}
    section(out, "1. DATABASE - KIỂM TRA CHỈ ĐỌC")
    add(out, f"Database: {DB_PATH}")

    if not DB_PATH.exists():
        add(out, "KHÔNG TÌM THẤY DATABASE.")
        return info

    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            add(out, f"PRAGMA integrity_check: {row[0] if row else 'UNKNOWN'}")
        except Exception as exc:
            add(out, f"PRAGMA integrity_check lỗi đọc: {exc}")

        try:
            fk = conn.execute("PRAGMA foreign_key_check").fetchall()
            add(out, f"PRAGMA foreign_key_check: {len(fk)} lỗi")
        except Exception as exc:
            add(out, f"PRAGMA foreign_key_check lỗi đọc: {exc}")

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        add(out, f"Tổng số bảng: {len(tables)}")

        for table in TARGET_TABLES:
            add(out)
            add(out, f"[BẢNG] {table}")
            if table not in tables:
                add(out, "  - Không tồn tại")
                info[table] = []
                continue

            cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            info[table] = cols
            count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            add(out, f"  - Số dòng: {count}")
            add(out, "  - Cột:")
            for col in cols:
                add(
                    out,
                    f"    {col[0]:>3} | {col[1]:<40} | {col[2]:<18} | "
                    f"NOT NULL={col[3]} | DEFAULT={col[4]} | PK={col[5]}",
                )

        section(out, "2. DATABASE - ĐỐI CHIẾU CỘT THEO NHÓM NGHIỆP VỤ")
        for group, terms in KEYWORDS.items():
            add(out)
            add(out, f"[{group}]")
            matches = []
            for table, cols in info.items():
                for col in cols:
                    name = str(col[1])
                    lowered = name.lower()
                    if any(term.lower() in lowered for term in terms):
                        matches.append((table, name, str(col[2])))
            if matches:
                for table, name, dtype in matches:
                    add(out, f"  - CÓ THỂ LIÊN QUAN: {table}.{name} ({dtype})")
            else:
                add(out, "  - Chưa thấy cột có tên tương ứng")
    finally:
        conn.close()

    return info


def inspect_models(out: list[str]) -> None:
    section(out, "3. SOURCE - MODEL SQLALCHEMY")

    model_files = []
    if (APP / "models.py").exists():
        model_files.append(APP / "models.py")
    if (APP / "models").exists():
        model_files.extend(sorted((APP / "models").rglob("*.py")))

    found = False
    for path in model_files:
        text = read_text(path)
        if not text:
            continue
        try:
            tree = ast.parse(text)
        except Exception as exc:
            add(out, f"{path.relative_to(PROJECT)}: AST lỗi: {exc}")
            continue

        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name not in TARGET_CLASSES:
                continue
            found = True
            add(out)
            add(out, f"[CLASS] {node.name}")
            add(out, f"File: {path.relative_to(PROJECT)}")
            add(out, f"Dòng: {node.lineno}-{node.end_lineno}")

            attrs = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    attrs.append(item.target.id)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            attrs.append(target.id)

            for name in attrs:
                add(out, f"  - {name}")

    if not found:
        add(out, "Không tìm thấy class mục tiêu trong model source")


def scan_source(out: list[str]) -> None:
    section(out, "4. SOURCE - DẤU VẾT NGHIỆP VỤ HIỆN CÓ")

    hits: dict[str, list[tuple[str, int, str]]] = {key: [] for key in KEYWORDS}

    for path in APP.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if "__pycache__" in path.parts:
            continue

        text = read_text(path)
        if not text:
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            for group, terms in KEYWORDS.items():
                if len(hits[group]) >= 40:
                    continue
                if any(term.lower() in lowered for term in terms):
                    snippet = " ".join(line.strip().split())
                    if len(snippet) > 180:
                        snippet = snippet[:177] + "..."
                    hits[group].append(
                        (str(path.relative_to(PROJECT)), line_no, snippet)
                    )

    for group in KEYWORDS:
        add(out)
        add(out, f"[{group}]")
        if not hits[group]:
            add(out, "  - Không tìm thấy dấu vết source")
            continue
        for rel, line_no, snippet in hits[group][:25]:
            add(out, f"  - {rel}:{line_no}: {snippet}")
        if len(hits[group]) > 25:
            add(out, f"  - ... còn {len(hits[group]) - 25} dòng khác")


def inspect_template(out: list[str]) -> None:
    section(out, "5. TEMPLATE THÔNG TIN NĂM HỌC HIỆN TẠI")
    path = APP / "templates" / "surveys" / "year_records.html"
    if not path.exists():
        add(out, f"Không tìm thấy: {path.relative_to(PROJECT)}")
        return

    text = read_text(path)
    add(out, f"File: {path.relative_to(PROJECT)}")
    add(out, f"Số dòng: {len(text.splitlines())}")

    labels = [
        "Tình trạng học tập",
        "Xã/phường hiện tại",
        "Trường hiện tại",
        "Lớp hiện tại",
        "Các chỉ báo mầm non",
        "Theo dõi trẻ khuyết tật",
        "Hoàn cảnh đặc biệt",
        "Ghi chú",
        "Lưu thông tin năm học",
        "Lưu và chuyển thành viên tiếp theo",
    ]

    for label in labels:
        status = "CÓ" if label.lower() in text.lower() else "KHÔNG"
        add(out, f"  - {label}: {status}")

    field_names = sorted(
        set(
            re.findall(
                r'''(?:name|id)=["']([A-Za-z_][A-Za-z0-9_\-]*)["']''',
                text,
                flags=re.IGNORECASE,
            )
        )
    )
    add(out)
    add(out, "Field name/id liên quan:")
    for name in field_names:
        lower = name.lower()
        if any(
            token in lower
            for token in (
                "school", "class", "status", "year", "disab", "indicator",
                "complete", "completion", "liter", "grade", "primary", "secondary"
            )
        ):
            add(out, f"  - {name}")


def summarize(out: list[str], db_info: dict[str, list[tuple]]) -> None:
    section(out, "6. KẾT LUẬN KHẢO SÁT TỰ ĐỘNG")

    year_cols = {
        str(row[1]).lower()
        for row in db_info.get("survey_person_year_records", [])
    }

    expected = {
        "Đối tượng điều tra XMC": ["is_literacy_target", "literacy_target", "xmc_target"],
        "Tình trạng XMC": ["literacy_status", "xmc_status"],
        "Hoàn thành lớp 3": ["completed_grade_3", "grade3_completed"],
        "Hoàn thành lớp 5": ["completed_grade_5", "grade5_completed"],
        "Hoàn thành CT Tiểu học": ["completed_primary_program", "primary_completed"],
        "Hoàn thành CT THCS": ["completed_lower_secondary_program", "lower_secondary_completed"],
        "Hướng học sau THCS": ["post_lower_secondary_path", "post_thcs_path"],
    }

    for label, candidates in expected.items():
        exact = [name for name in candidates if name.lower() in year_cols]
        if exact:
            add(out, f"[CÓ SẴN] {label}: {', '.join(exact)}")
        else:
            add(out, f"[CHƯA THẤY TÊN CHUẨN] {label}")

    add(out)
    add(out, "LƯU Ý:")
    add(out, " - Đây chỉ là khảo sát tự động, chưa tạo cột mới")
    add(out, " - Không ALTER TABLE / INSERT / UPDATE / DELETE")
    add(out, " - Các chỉ báo Mầm non hiện có phải giữ nguyên ở bước sau")
    add(out, " - Bước 13B-11.13.1 chỉ tạo trường thực sự còn thiếu sau khi đọc báo cáo này")


def main() -> int:
    out: list[str] = []

    add(out, "=" * 112)
    add(out, "BÀI 13B-11.13.0 - KHẢO SÁT MODEL / DATABASE CHO MN - TH - THCS - XMC")
    add(out, "=" * 112)
    add(out)
    add(out, "CHẾ ĐỘ: CHỈ ĐỌC")
    add(out, f"Project: {PROJECT}")
    add(out, f"Python: {sys.executable}")
    add(out, f"Thời điểm: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    add(out)
    add(out, "KHÔNG THỰC HIỆN:")
    add(out, " - Không sửa source")
    add(out, " - Không ALTER TABLE")
    add(out, " - Không INSERT/UPDATE/DELETE")
    add(out, " - Không thay đổi các chỉ báo Mầm non hiện có")

    try:
        db_info = inspect_database(out)
        inspect_models(out)
        scan_source(out)
        inspect_template(out)
        summarize(out, db_info)

        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        REPORT.write_text("\n".join(out), encoding="utf-8")

        print("\n".join(out[:70]))
        if len(out) > 70:
            print("\n... (đã rút gọn trên màn hình) ...\n")
        print("=" * 112)
        print("KHẢO SÁT BÀI 13B-11.13.0 HOÀN THÀNH")
        print("=" * 112)
        print("Không có source/database nào bị thay đổi.")
        print("Báo cáo đầy đủ:")
        print(REPORT)
        return 0

    except Exception:
        traceback.print_exc()
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            out.append("")
            out.append("KHẢO SÁT DỪNG DO LỖI")
            out.append(traceback.format_exc())
            REPORT.write_text("\n".join(out), encoding="utf-8")
            print("Báo cáo lỗi:")
            print(REPORT)
        except Exception:
            pass
        print("Database/source không bị thay đổi.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
