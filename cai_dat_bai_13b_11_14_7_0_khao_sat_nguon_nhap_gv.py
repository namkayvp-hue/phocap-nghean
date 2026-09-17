from __future__ import annotations

import os
import re
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

DB = PROJECT / "data" / "phocap.db"
APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

REPORT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_14_7_0_khao_sat_nguon_nhap_gv_{STAMP}.txt"
)

SOURCE_EXT = {".py", ".html", ".htm"}

SKIP_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "exports",
    "backup",
    "backups",
}

KEYWORDS = (
    "staff",
    "đội ngũ",
    "giáo viên",
    "nhân viên",
    "cán bộ quản lý",
    "hợp đồng",
    "trình độ",
    "chuẩn nghề nghiệp",
    "chính sách",
    "chế độ",
    "lớp ghép",
    "ghep",
    "mixed",
    "multigrade",
    "teaching",
    "qualification",
    "professional",
    "employment",
)


EXPECTED_FIELDS = (
    (
        "Loại nhân sự / vị trí việc làm",
        (
            "staff_type",
            "position",
            "job_position",
            "position_code",
            "role",
        ),
    ),
    (
        "Loại hợp đồng / hình thức làm việc",
        (
            "employment_type",
            "contract_type",
            "employment_status",
        ),
    ),
    (
        "Trình độ đào tạo",
        (
            "qualification_level",
            "qualification",
            "degree",
            "training_level",
        ),
    ),
    (
        "Chuyên ngành / môn dạy",
        (
            "major",
            "specialization",
            "subject",
            "teaching_subject",
        ),
    ),
    (
        "Chuẩn trình độ đào tạo",
        (
            "meets_training_standard",
            "training_standard",
        ),
    ),
    (
        "Chuẩn nghề nghiệp",
        (
            "professional_standard",
            "professional_standard_rating",
            "professional_rating",
            "teacher_standard",
        ),
    ),
    (
        "Kết quả đánh giá/xếp loại",
        (
            "evaluation_result",
            "rating",
            "assessment_result",
        ),
    ),
    (
        "Trạng thái công tác",
        (
            "status",
            "work_status",
            "employment_status",
        ),
    ),
    (
        "Lớp phụ trách",
        (
            "class_id",
            "homeroom_class_id",
            "assigned_class_id",
        ),
    ),
    (
        "GV dạy lớp ghép",
        (
            "teaches_multigrade",
            "teaches_combined_class",
            "is_multigrade_teacher",
            "mixed_class_teacher",
        ),
    ),
    (
        "Chương trình lớp ghép Có/Không",
        (
            "multigrade_program",
            "has_multigrade_program",
            "combined_class_program",
        ),
    ),
    (
        "Chế độ/chính sách",
        (
            "policy_code",
            "policy_name",
            "policy",
            "allowance",
            "benefit",
        ),
    ),
)


def normalize(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower(),
    )


def read_text(path: Path) -> str:
    try:
        return path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )
    except Exception:
        return ""


def source_files() -> list[Path]:
    result = []

    for path in APP.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in SOURCE_EXT:
            continue

        if any(
            part.lower() in SKIP_DIRS
            for part in path.parts
        ):
            continue

        result.append(path)

    return sorted(result)


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        is not None
    )


def columns(
    conn: sqlite3.Connection,
    table: str,
) -> list[str]:
    if not table_exists(conn, table):
        return []

    return [
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    ]


def count(
    conn: sqlite3.Connection,
    table: str,
) -> int:
    return int(
        conn.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    )


def line(out: list[str], text: str = "") -> None:
    out.append(text)


def find_related_files(
    files: list[Path],
) -> list[tuple[Path, list[str]]]:
    result = []

    for path in files:
        text = normalize(
            read_text(path)
        )

        hits = [
            keyword
            for keyword in KEYWORDS
            if normalize(keyword) in text
        ]

        if hits:
            result.append(
                (path, hits)
            )

    result.sort(
        key=lambda item: (
            -len(item[1]),
            str(item[0]),
        )
    )

    return result


def main() -> int:
    print("=" * 124)
    print(
        "BÀI 13B-11.14.7.0 - "
        "KHẢO SÁT NGUỒN NHẬP ĐỘI NGŨ/GV PHỤC VỤ BIỂU GV"
    )
    print("=" * 124)
    print()
    print("CHỈ ĐỌC:")
    print(" - Không sửa source/template.")
    print(" - Không sửa database.")
    print(" - Không ALTER/INSERT/UPDATE/DELETE.")
    print()
    print("MỤC TIÊU:")
    print(
        " - Xác định các trường GV đã có trong staff_year_records."
    )
    print(
        " - Xác định phần còn thiếu để phục vụ biểu GV."
    )
    print(
        " - Đặc biệt kiểm tra: GV dạy lớp ghép + chương trình lớp ghép."
    )
    print(
        " - Kiểm tra hợp đồng, trình độ, chuẩn nghề nghiệp, chính sách."
    )
    print(
        " - Không khảo sát lại CSVC/trường/lớp."
    )
    print()

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    EXPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    out: list[str] = []

    line(out, "=" * 124)
    line(
        out,
        "BÁO CÁO BÀI 13B-11.14.7.0 - "
        "KHẢO SÁT NGUỒN NHẬP ĐỘI NGŨ/GV",
    )
    line(out, "=" * 124)
    line(out, f"Project: {PROJECT}")
    line(out, f"Database: {DB}")
    line(out, f"Thời điểm: {datetime.now():%d/%m/%Y %H:%M:%S}")
    line(out)

    conn = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        line(out, "I. KIỂM TRA DATABASE")
        line(out, "-" * 90)
        line(out, f"integrity_check: {integrity}")
        line(out, f"foreign_key_check: {len(fk)} lỗi")
        line(out)

        target_tables = (
            "staff_members",
            "staff_year_records",
            "school_staff_year_summaries",
            "staff_policy_year_records",
            "classes",
        )

        table_cols = {}

        for table in target_tables:
            line(out, f"[{table}]")

            if not table_exists(conn, table):
                line(out, "  KHÔNG CÓ BẢNG")
                line(out)
                continue

            cols = columns(conn, table)
            table_cols[table] = cols

            line(out, f"  rows: {count(conn, table)}")
            line(out, "  columns:")
            for col in cols:
                line(out, f"    - {col}")
            line(out)

        staff_year_cols = set(
            table_cols.get(
                "staff_year_records",
                [],
            )
        )

        policy_cols = set(
            table_cols.get(
                "staff_policy_year_records",
                [],
            )
        )

        line(out, "II. MA TRẬN TRƯỜNG DỮ LIỆU CẦN CHO BIỂU GV")
        line(out, "-" * 90)

        for label, candidates in EXPECTED_FIELDS:
            found_staff = [
                c
                for c in candidates
                if c in staff_year_cols
            ]

            found_policy = [
                c
                for c in candidates
                if c in policy_cols
            ]

            found = (
                found_staff
                + found_policy
            )

            if found:
                line(
                    out,
                    f"[CÓ] {label}: "
                    + ", ".join(found),
                )
            else:
                line(
                    out,
                    f"[THIẾU/CHƯA THẤY] {label}",
                )

        line(out)
        line(out, "III. MẪU DỮ LIỆU staff_year_records")
        line(out, "-" * 90)

        if table_exists(conn, "staff_year_records"):
            sample_cols = [
                col
                for col in (
                    "id",
                    "staff_member_id",
                    "school_id",
                    "school_year_id",
                    "employment_type",
                    "position",
                    "job_position",
                    "qualification_level",
                    "qualification",
                    "major",
                    "specialization",
                    "teaching_subject",
                    "professional_standard",
                    "professional_standard_rating",
                    "evaluation_result",
                    "status",
                    "class_id",
                )
                if col in staff_year_cols
            ]

            if sample_cols:
                sql = (
                    "SELECT "
                    + ", ".join(
                        f'"{c}"'
                        for c in sample_cols
                    )
                    + " FROM staff_year_records "
                    + "ORDER BY id DESC LIMIT 15"
                )

                rows = conn.execute(
                    sql
                ).fetchall()

                line(
                    out,
                    "Cột mẫu: "
                    + ", ".join(sample_cols),
                )

                for row in rows:
                    line(
                        out,
                        "  "
                        + repr(row),
                    )
            else:
                line(
                    out,
                    "Không có cột phù hợp để lấy mẫu.",
                )

        line(out)
        line(out, "IV. THỐNG KÊ NULL / CÓ GIÁ TRỊ CÁC TRƯỜNG QUAN TRỌNG")
        line(out, "-" * 90)

        important = [
            c
            for c in (
                "employment_type",
                "position",
                "job_position",
                "qualification_level",
                "qualification",
                "major",
                "specialization",
                "teaching_subject",
                "professional_standard",
                "professional_standard_rating",
                "evaluation_result",
                "status",
                "class_id",
            )
            if c in staff_year_cols
        ]

        for col in important:
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(
                        CASE
                            WHEN "{col}" IS NOT NULL
                             AND TRIM(CAST("{col}" AS TEXT)) <> ''
                            THEN 1 ELSE 0
                        END
                    ) AS has_value
                FROM staff_year_records
                """
            ).fetchone()

            total = int(
                row[0] or 0
            )

            has_value = int(
                row[1] or 0
            )

            line(
                out,
                f" - {col}: "
                f"{has_value}/{total} có giá trị",
            )

    finally:
        conn.close()

    files = source_files()
    related = find_related_files(files)

    line(out)
    line(out, "V. SOURCE / TEMPLATE LIÊN QUAN ĐỘI NGŨ")
    line(out, "-" * 90)
    line(
        out,
        f"Tổng file app quét: {len(files)}",
    )

    for path, hits in related[:35]:
        line(
            out,
            " - "
            + str(
                path.relative_to(PROJECT)
            ),
        )
        line(
            out,
            "   từ khóa: "
            + ", ".join(
                hits[:12]
            ),
        )

    line(out)
    line(out, "VI. KIỂM TRA DẤU VẾT LỚP GHÉP TRONG SOURCE")
    line(out, "-" * 90)

    multigrade_hits = []

    for path in files:
        text = read_text(path)

        low = normalize(text)

        if any(
            key in low
            for key in (
                "lớp ghép",
                "lop ghep",
                "multigrade",
                "combined class",
                "mixed class",
            )
        ):
            multigrade_hits.append(path)

    if multigrade_hits:
        for path in multigrade_hits:
            line(
                out,
                " - "
                + str(
                    path.relative_to(PROJECT)
                ),
            )
    else:
        line(
            out,
            " - Chưa thấy source hiện có xử lý GV dạy lớp ghép.",
        )

    line(out)
    line(out, "VII. KẾT LUẬN THIẾT KẾ CHO BÀI 14.7.1")
    line(out, "-" * 90)
    line(
        out,
        "1. Tận dụng staff_members + staff_year_records; "
        "không tạo lại hồ sơ GV.",
    )
    line(
        out,
        "2. Chỉ bổ sung các trường thực sự thiếu cho biểu GV.",
    )
    line(
        out,
        "3. Lớp ghép ở Đội ngũ chỉ là thuộc tính của GV: "
        "Có dạy lớp ghép hay không.",
    )
    line(
        out,
        "4. Chương trình lớp ghép là thuộc tính nghiệp vụ GV/đơn vị, "
        "không quản lý lại lớp.",
    )
    line(
        out,
        "5. Chế độ/chính sách nhiều giá trị dùng staff_policy_year_records.",
    )
    line(
        out,
        "6. GV/lớp và các tỷ lệ không nhập tay; "
        "hệ thống tự tính từ GV + số lớp CSVC.",
    )
    line(out)
    line(
        out,
        "CAM KẾT: BÀI 14.7.0 CHỈ ĐỌC, "
        "KHÔNG THAY ĐỔI SOURCE/DATABASE.",
    )

    REPORT.write_text(
        "\n".join(out),
        encoding="utf-8-sig",
    )

    print("Khảo sát hoàn thành.")
    print("Báo cáo:", REPORT)
    print("Database/source: KHÔNG THAY ĐỔI.")
    print("integrity_check:", integrity)
    print("foreign_key_check:", len(fk), "lỗi")
    print()
    print("=" * 124)
    print("BÀI 13B-11.14.7.0 KHẢO SÁT THÀNH CÔNG")
    print("=" * 124)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        print()
        print(
            "KHẢO SÁT GẶP LỖI. "
            "Bài này chỉ đọc nên source/database không bị thay đổi."
        )
        raise
