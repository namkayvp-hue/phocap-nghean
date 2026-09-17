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

APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_15_0_khao_sat_nguon_thcs_01_ttn_{STAMP}.txt"
)

TABLES = (
    "survey_person_year_records",
    "survey_people",
    "survey_person_events",
    "school_years",
    "classes",
    "schools",
)

SOURCE_FILES = (
    APP / "survey_models.py",
    APP / "routers" / "surveys.py",
    APP / "templates" / "surveys" / "year_records.html",
    APP / "pcgd_xmc_report_builders_v1.py",
)

SEARCH_TOKENS = (
    "completed_lower_secondary_program",
    "post_lower_secondary_path",
    "learning_status",
    "GDTX",
    "GDNN",
    "PHO_THONG",
    "pho_thong",
    "tai_cho",
    "tại chỗ",
    "di_hoc_noi_khac",
    "đi học nơi khác",
    "noi_khac_den",
    "nơi khác đến",
    "bo_hoc",
    "bỏ học",
    "dropout",
    "drop_out",
    "school_name_reported",
    "class_name_reported",
    "school_id",
    "class_id",
)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""

    return path.read_text(
        encoding="utf-8-sig",
        errors="ignore",
    )


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


def table_columns(
    conn: sqlite3.Connection,
    table: str,
) -> list[tuple]:
    if not table_exists(conn, table):
        return []

    return conn.execute(
        f'PRAGMA table_info("{table}")'
    ).fetchall()


def table_count(
    conn: sqlite3.Connection,
    table: str,
) -> int:
    if not table_exists(conn, table):
        return -1

    return int(
        conn.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    )


def find_lines(
    text: str,
    token: str,
    limit: int = 12,
) -> list[tuple[int, str]]:
    result = []

    low_token = token.lower()

    for lineno, line in enumerate(
        text.splitlines(),
        start=1,
    ):
        if low_token in line.lower():
            result.append(
                (
                    lineno,
                    line.strip(),
                )
            )

        if len(result) >= limit:
            break

    return result


def find_related_sources() -> list[Path]:
    result: list[Path] = []

    for path in APP.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in {
            ".py",
            ".html",
            ".htm",
        }:
            continue

        if any(
            part.lower() in {
                ".venv",
                "venv",
                "__pycache__",
                "backup",
                "backups",
            }
            for part in path.parts
        ):
            continue

        text = read_text(path)

        low = text.lower()

        if any(
            token.lower() in low
            for token in SEARCH_TOKENS
        ):
            result.append(path)

    return sorted(result)


def main() -> int:
    print("=" * 128)
    print(
        "BÀI 13B-11.15.0 - "
        "KHẢO SÁT NGUỒN NHẬP PHỤC VỤ MẪU THCS-01-TTN"
    )
    print("=" * 128)
    print()
    print("MẪU CẦN PHỤC VỤ:")
    print(" - Tại chỗ.")
    print(" - Đi học nơi khác.")
    print(" - Nơi khác đến.")
    print(" - Chương trình Phổ thông / GDTX / GDNN.")
    print(" - Bỏ học.")
    print()
    print("NGUYÊN TẮC:")
    print(
        " - Chỉ thu thập dữ liệu gốc từng đối tượng; "
        "không nhập số tổng hợp bằng tay."
    )
    print(
        " - Tuổi, giới tính, dân tộc, khuyết tật, lớp "
        "sẽ tận dụng dữ liệu hiện có nếu đã đủ."
    )
    print(
        " - Bài này CHỈ ĐỌC; không sửa source/database."
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

    def add(text: str = "") -> None:
        out.append(text)

    add("=" * 128)
    add(
        "BÁO CÁO BÀI 13B-11.15.0 - "
        "KHẢO SÁT NGUỒN THCS-01-TTN"
    )
    add("=" * 128)
    add(f"Project: {PROJECT}")
    add(f"Database: {DB}")
    add(f"Thời điểm: {datetime.now():%d/%m/%Y %H:%M:%S}")
    add()

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

        fk_rows = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        add("I. KIỂM TRA DATABASE")
        add("-" * 100)
        add(f"integrity_check: {integrity}")
        add(
            f"foreign_key_check: "
            f"{len(fk_rows)} lỗi"
        )
        add()

        add("II. CẤU TRÚC CÁC BẢNG LIÊN QUAN")
        add("-" * 100)

        for table in TABLES:
            add(f"[{table}]")

            if not table_exists(
                conn,
                table,
            ):
                add("  KHÔNG CÓ BẢNG")
                add()
                continue

            add(
                f"  rows: "
                f"{table_count(conn, table)}"
            )

            for row in table_columns(
                conn,
                table,
            ):
                # cid, name, type, notnull, default, pk
                add(
                    "  - "
                    f"{row[1]} | "
                    f"{row[2]} | "
                    f"notnull={row[3]} | "
                    f"default={row[4]} | "
                    f"pk={row[5]}"
                )

            add()

        add("III. KIỂM TRA TRƯỜNG ĐÃ CÓ / CÒN THIẾU")
        add("-" * 100)

        year_cols = {
            str(row[1])
            for row in table_columns(
                conn,
                "survey_person_year_records",
            )
        }

        people_cols = {
            str(row[1])
            for row in table_columns(
                conn,
                "survey_people",
            )
        }

        field_checks = (
            (
                "Tuổi/năm sinh",
                (
                    "date_of_birth",
                    "birth_date",
                    "year_of_birth",
                ),
                people_cols,
            ),
            (
                "Giới tính",
                (
                    "gender",
                    "sex",
                ),
                people_cols,
            ),
            (
                "Dân tộc",
                (
                    "ethnic_group",
                    "ethnicity",
                ),
                people_cols,
            ),
            (
                "Tình trạng học tập",
                (
                    "learning_status",
                ),
                year_cols,
            ),
            (
                "Trường hiện tại",
                (
                    "school_id",
                    "school_name_reported",
                ),
                year_cols,
            ),
            (
                "Lớp hiện tại",
                (
                    "class_id",
                    "class_name_reported",
                ),
                year_cols,
            ),
            (
                "Hoàn thành THCS",
                (
                    "completed_lower_secondary_program",
                ),
                year_cols,
            ),
            (
                "Hướng sau THCS",
                (
                    "post_lower_secondary_path",
                ),
                year_cols,
            ),
            (
                "Tại chỗ / đi học nơi khác / nơi khác đến",
                (
                    "thcs_study_location",
                    "study_location_scope",
                    "education_location_status",
                ),
                year_cols,
            ),
            (
                "Chương trình PT / GDTX / GDNN",
                (
                    "thcs_program_type",
                    "education_program_type",
                    "study_program_type",
                ),
                year_cols,
            ),
            (
                "Bỏ học",
                (
                    "is_dropout",
                    "dropped_out",
                    "dropout_status",
                    "dropout_date",
                ),
                year_cols,
            ),
        )

        for label, candidates, cols in field_checks:
            found = [
                field
                for field in candidates
                if field in cols
            ]

            if found:
                add(
                    f"[CÓ] {label}: "
                    + ", ".join(found)
                )
            else:
                add(
                    f"[CHƯA THẤY] {label}"
                )

        add()
        add("IV. MẪU DỮ LIỆU NĂM HỌC HIỆN CÓ")
        add("-" * 100)

        if table_exists(
            conn,
            "survey_person_year_records",
        ):
            useful = [
                column
                for column in (
                    "id",
                    "survey_person_id",
                    "school_year_id",
                    "learning_status",
                    "school_id",
                    "class_id",
                    "school_name_reported",
                    "class_name_reported",
                    "completed_lower_secondary_program",
                    "post_lower_secondary_path",
                    "disability_status",
                    "disability_type",
                    "disability_level",
                )
                if column in year_cols
            ]

            if useful:
                sql = (
                    "SELECT "
                    + ", ".join(
                        f'"{col}"'
                        for col in useful
                    )
                    + ' FROM "survey_person_year_records" '
                    + "ORDER BY id DESC LIMIT 20"
                )

                add(
                    "Cột mẫu: "
                    + ", ".join(useful)
                )

                for row in conn.execute(
                    sql
                ).fetchall():
                    add("  " + repr(row))

        add()
        add("V. KIỂM TRA DẤU VẾT SOURCE")
        add("-" * 100)

        paths = list(
            dict.fromkeys(
                list(SOURCE_FILES)
                + find_related_sources()
            )
        )

        for path in paths:
            if not path.exists():
                continue

            text = read_text(path)

            matches = []

            for token in SEARCH_TOKENS:
                lines = find_lines(
                    text,
                    token,
                    limit=4,
                )

                if lines:
                    matches.append(
                        (
                            token,
                            lines,
                        )
                    )

            if not matches:
                continue

            add(
                f"[{path.relative_to(PROJECT)}]"
            )

            for token, lines in matches:
                add(
                    f"  token: {token}"
                )

                for lineno, content in lines:
                    add(
                        f"    L{lineno}: "
                        f"{content[:240]}"
                    )

            add()

        add("VI. ĐỀ XUẤT DỮ LIỆU GỐC CHO THCS-01-TTN")
        add("-" * 100)
        add(
            "1. thcs_study_location: "
            "CHUA_XAC_DINH / TAI_CHO / DI_HOC_NOI_KHAC / NOI_KHAC_DEN."
        )
        add(
            "2. thcs_program_type: "
            "CHUA_XAC_DINH / PHO_THONG / GDTX / GDNN."
        )
        add(
            "3. is_dropout: "
            "NULL=Chưa xác định / 1=Có / 0=Không."
        )
        add(
            "4. Không tạo cột tuổi, giới tính, dân tộc, khuyết tật, "
            "trường, lớp nếu nguồn hiện có đã đủ."
        )
        add(
            "5. Số liệu báo cáo theo tuổi 11-18, lớp 6-9/THCS, "
            "PT-GDTX-GDNN sẽ tự tổng hợp từ hồ sơ từng người."
        )
        add()
        add(
            "CAM KẾT: BÀI 13B-11.15.0 CHỈ ĐỌC, "
            "KHÔNG THAY ĐỔI SOURCE/DATABASE."
        )

    finally:
        conn.close()

    REPORT.write_text(
        "\n".join(out),
        encoding="utf-8-sig",
    )

    print("Khảo sát hoàn thành.")
    print("Báo cáo:", REPORT)
    print(
        "Database/source: KHÔNG THAY ĐỔI."
    )
    print(
        "integrity_check:",
        integrity,
    )
    print(
        "foreign_key_check:",
        len(fk_rows),
        "lỗi",
    )
    print()
    print("=" * 128)
    print(
        "BÀI 13B-11.15.0 KHẢO SÁT THÀNH CÔNG"
    )
    print("=" * 128)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )
    except Exception:
        traceback.print_exc()
        print()
        print(
            "KHẢO SÁT GẶP LỖI. "
            "Bài này chỉ đọc nên source/database không bị thay đổi."
        )
        raise
